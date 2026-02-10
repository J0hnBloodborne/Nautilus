"""SmashyStream (F / video1) — base64-decoded HLS + subtitle parsing."""
from __future__ import annotations
import re, base64
from ..base import EmbedResult, Stream, Caption
from ..fetcher import Fetcher
from ..runner import register_embed

# Obfuscation key segments used in base64 decode
_B_KEYS = [
    "U0ZML2RVN0IvRGx4",
    "MGNhL0JWb0kvTlM5",
    "Ym94LzJTSS9aU0Zj",
    "SGJ0L1dGakIvN0dX",
    "eE52L1QwOC96N0Yz",
]

LANG_MAP = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "portuguese": "pt", "russian": "ru", "japanese": "ja",
    "korean": "ko", "chinese": "zh", "arabic": "ar", "hindi": "hi",
    "turkish": "tr",
}


def _decode(s: str) -> str:
    b64 = s[2:]
    for i in range(4, -1, -1):
        b64 = b64.replace(f"//{_B_KEYS[i]}", "")
    return base64.b64decode(b64).decode("utf-8")


@register_embed
class SmashyStreamF:
    id = "smashystream-f"
    name = "SmashyStream (F)"
    rank = 71

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        res = await fetcher.get_json(url, headers={"Referer": url})

        source_urls = res.get("sourceUrls", [])
        if not source_urls:
            raise ValueError("SmashyStream: no sources")

        playlist = _decode(source_urls[0])
        if ".m3u8" not in playlist:
            raise ValueError("SmashyStream: failed to decode HLS URL")

        captions = []
        subs_raw = res.get("subtitles")
        if subs_raw and isinstance(subs_raw, str):
            for m in re.finditer(r'\[([^\]]+)\](https?://\S+?)(?=,\[|$)', subs_raw):
                label = m.group(1).split(" - ")[0].strip().lower()
                sub_url = m.group(2).replace(",", "")
                lang = LANG_MAP.get(label, label[:2] if label else "en")
                fmt = "vtt" if sub_url.endswith(".vtt") else "srt"
                captions.append(Caption(url=sub_url, lang=lang, format=fmt))

        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=playlist, captions=captions)
        ])
