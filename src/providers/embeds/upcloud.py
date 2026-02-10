"""
UpCloud — rabbitstream.net AES decryption with dynamic key extraction.
Disabled: the key extraction from player JS is fragile.
"""
from __future__ import annotations
import re, json, base64, time
from ..base import EmbedResult, Stream, Caption
from ..fetcher import Fetcher
from ..runner import register_embed

ORIGIN = "https://rabbitstream.net"
LANG_MAP = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "portuguese": "pt", "russian": "ru", "japanese": "ja",
    "korean": "ko", "chinese": "zh", "arabic": "ar", "hindi": "hi",
    "turkish": "tr", "dutch": "nl", "polish": "pl",
}


def _extract_key(script: str):
    """Extract AES key pairs from rabbitstream player JS."""
    start = script.rfind("switch")
    end = script.find("partKeyStartPosition")
    if start == -1 or end == -1:
        return None
    body = script[start:end]
    pairs = re.findall(r":([a-zA-Z0-9]+)=([a-zA-Z0-9]+),([a-zA-Z0-9]+)=([a-zA-Z0-9]+);", body)
    if not pairs:
        # Alternate pattern
        pairs2 = re.findall(r":[a-zA-Z0-9]+=([a-zA-Z0-9]+),[a-zA-Z0-9]+=([a-zA-Z0-9]+);", body)
        nums = []
        for var1, var2 in pairs2:
            inner = []
            for v in (var1, var2):
                m = list(re.finditer(rf"{v}=0x([a-fA-F0-9]+)", script))
                if not m:
                    return None
                inner.append(int(m[-1].group(1), 16))
            nums.append(tuple(inner))
        return nums
    return None


def _aes_decrypt(data_b64: str, key: str) -> str:
    """AES-256-CBC decrypt (CryptoJS-compatible)."""
    try:
        from Crypto.Cipher import AES as _AES
        from Crypto.Protocol.KDF import PBKDF2
        import hashlib
        raw = base64.b64decode(data_b64)
        # CryptoJS format: Salted__<8 bytes salt><ciphertext>
        if raw[:8] == b"Salted__":
            salt = raw[8:16]
            ct = raw[16:]
        else:
            salt = b""
            ct = raw

        # CryptoJS key derivation: MD5-based EVP_BytesToKey
        def evp_bytes_to_key(password, salt, key_len=32, iv_len=16):
            dtot = b""
            d = b""
            while len(dtot) < key_len + iv_len:
                d = hashlib.md5(d + password.encode() + salt).digest()
                dtot += d
            return dtot[:key_len], dtot[key_len:key_len + iv_len]

        k, iv = evp_bytes_to_key(key, salt)
        cipher = _AES.new(k, _AES.MODE_CBC, iv)
        pt = cipher.decrypt(ct)
        # PKCS7 unpad
        pad = pt[-1]
        if isinstance(pad, int):
            pt = pt[:-pad]
        else:
            pt = pt[:-ord(pad)]
        return pt.decode("utf-8")
    except ImportError:
        raise RuntimeError("pycryptodome required for upcloud: pip install pycryptodome")


@register_embed
class UpCloudEmbed:
    id = "upcloud"
    name = "UpCloud"
    rank = 200
    disabled = True

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        parsed = url.replace("embed-5", "embed-4")
        from urllib.parse import urlparse
        u = urlparse(parsed)
        data_id = u.path.rstrip("/").split("/")[-1]
        origin = f"{u.scheme}://{u.netloc}"

        stream_res = await fetcher.get_json(
            f"{origin}/ajax/embed-4/getSources?id={data_id}",
            headers={"Referer": origin, "X-Requested-With": "XMLHttpRequest"},
        )

        sources_raw = stream_res.get("sources", "")
        sources = None

        # Check if sources is already JSON
        if isinstance(sources_raw, list):
            sources = sources_raw[0] if sources_raw else None
        elif isinstance(sources_raw, str):
            try:
                parsed_src = json.loads(sources_raw)
                sources = parsed_src[0] if isinstance(parsed_src, list) else parsed_src
            except (json.JSONDecodeError, ValueError):
                # Encrypted — fetch player JS for key
                script = await fetcher.get(
                    f"https://rabbitstream.net/js/player/prod/e4-player.min.js",
                    params={"v": str(int(time.time()))},
                )
                key_pairs = _extract_key(script)
                if not key_pairs:
                    raise ValueError("UpCloud key extraction failed")

                extracted_key = ""
                stripped = sources_raw
                offset = 0
                for a, b in key_pairs:
                    start = a + offset
                    end = start + b
                    extracted_key += sources_raw[start:end]
                    stripped = stripped[:start - offset] + stripped[end - offset:]
                    offset += b

                decrypted = _aes_decrypt(stripped, extracted_key)
                parsed_stream = json.loads(decrypted)
                sources = parsed_stream[0] if isinstance(parsed_stream, list) else parsed_stream

        if not sources:
            raise ValueError("UpCloud source not found")

        playlist = sources.get("file", "")
        captions = []
        for track in stream_res.get("tracks", []):
            if track.get("kind") != "captions":
                continue
            label = track.get("label", "").split()[0].lower()
            lang = LANG_MAP.get(label, label[:2] if label else "en")
            file_url = track.get("file", "")
            if file_url:
                fmt = "vtt" if file_url.endswith(".vtt") else "srt"
                captions.append(Caption(url=file_url, lang=lang, format=fmt))

        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=playlist, captions=captions,
                   headers={"Referer": ORIGIN + "/", "Origin": ORIGIN})
        ])
