"""
VidPlay — RC4 decryption with keys from GitHub, futoken generation → HLS.
"""
from __future__ import annotations
import re, json
from urllib.parse import urlparse, parse_qs, urlencode
from ..base import EmbedResult, Stream, Caption
from ..fetcher import Fetcher
from ..runner import register_embed

VIDPLAY_BASE = "https://vidplay.online"
KEYS_URL = "https://github.com/Ciarands/vidsrc-keys/blob/main/keys.json"

LANG_MAP = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "portuguese": "pt", "russian": "ru", "japanese": "ja",
    "korean": "ko", "chinese": "zh", "arabic": "ar", "hindi": "hi",
    "turkish": "tr", "dutch": "nl", "polish": "pl",
}


def _rc4(key: str, data) -> str:
    """RC4 stream cipher decode."""
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + ord(key[i % len(key)])) % 256
        state[i], state[j] = state[j], state[i]

    j = 0
    i = 0
    result = []
    for idx in range(len(data)):
        i = (i + 1) % 256
        j = (j + state[i]) % 256
        state[i], state[j] = state[j], state[i]
        if isinstance(data[idx], str):
            result.append(chr(ord(data[idx]) ^ state[(state[i] + state[j]) % 256]))
        else:
            result.append(chr(data[idx] ^ state[(state[i] + state[j]) % 256]))
    return "".join(result)


import base64 as _b64


def _decode_base64_url_safe(s: str) -> bytes:
    std = s.replace("_", "/").replace("-", "+")
    decoded = _b64.b64decode(std)
    return decoded


@register_embed
class VidPlayEmbed:
    id = "vidplay"
    name = "VidPlay"
    rank = 401

    async def _get_keys(self, fetcher: Fetcher) -> list:
        html = await fetcher.get(KEYS_URL)
        m = re.search(r'"rawLines":\s*\[([\s\S]*?)\]', html)
        if not m:
            raise ValueError("VidPlay: no keys found")
        raw = m.group(1)
        quote = '"'
        start = raw.index(quote)
        keys = json.loads(raw[start:] + "]")
        if isinstance(keys, str):
            keys = json.loads(keys)
        return keys

    async def _get_encoded_id(self, url: str, fetcher: Fetcher) -> str:
        parsed = urlparse(url)
        vid_id = parsed.path.replace("/e/", "").strip("/")
        keys = await self._get_keys(fetcher)

        decoded1 = _rc4(keys[0], vid_id)
        decoded2 = _rc4(keys[1], decoded1)
        encoded = _b64.b64encode(decoded2.encode()).decode()
        return encoded.replace("/", "_")

    async def _get_fu_token(self, url: str, fetcher: Fetcher) -> str:
        encoded_id = await self._get_encoded_id(url, fetcher)
        fu_html = await fetcher.get(
            f"{VIDPLAY_BASE}/futoken",
            headers={"Referer": url},
        )
        fu_key_m = re.search(r"var\s+k\s*=\s*'([^']+)'", fu_html)
        if not fu_key_m:
            raise ValueError("VidPlay: fuKey not found")
        fu_key = fu_key_m.group(1)
        tokens = []
        for i in range(len(encoded_id)):
            tokens.append(str(ord(fu_key[i % len(fu_key)]) + ord(encoded_id[i])))
        return f"{fu_key},{','.join(tokens)}"

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        fu_token = await self._get_fu_token(url, fetcher)

        # Build mediainfo URL with original query params
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        params = {k: v[0] for k, v in qs.items()}
        params["autostart"] = "true"

        media_url = f"{VIDPLAY_BASE}/mediainfo/{fu_token}?{urlencode(params)}"

        res = await fetcher.get_json(media_url, headers={"Referer": url})

        if isinstance(res.get("result"), (int, float)):
            raise ValueError("VidPlay: file not found")

        result = res["result"]
        source = result["sources"][0]["file"]

        captions = []
        sub_info = params.get("sub.info")
        if sub_info:
            try:
                subs = await fetcher.get_json(sub_info)
                for sub in (subs if isinstance(subs, list) else []):
                    label = sub.get("label", "").split()[0].lower()
                    lang = LANG_MAP.get(label, label[:2] if label else "en")
                    f_url = sub.get("file", "")
                    if f_url:
                        fmt = "vtt" if f_url.endswith(".vtt") else "srt"
                        captions.append(Caption(url=f_url, lang=lang, format=fmt))
            except Exception:
                pass

        origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=source, captions=captions,
                   headers={"Referer": origin, "Origin": origin})
        ])
