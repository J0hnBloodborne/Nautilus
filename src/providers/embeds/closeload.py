"""CloseLoad — packed JS + caption track extraction."""
from __future__ import annotations
import re
from ..base import EmbedResult, Stream, Caption
from ..fetcher import Fetcher
from ..runner import register_embed
from .. import unpacker

REFERER = "https://ridomovies.tv/"
FILE_RE = re.compile(r'file:"([^"]+)"')
TRACK_RE = re.compile(r'<track\s+[^>]*src="([^"]+)"[^>]*label="([^"]*)"[^>]*>', re.IGNORECASE)

LANG_MAP = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "portuguese": "pt", "russian": "ru", "japanese": "ja",
    "korean": "ko", "chinese": "zh", "arabic": "ar", "hindi": "hi",
    "turkish": "tr", "dutch": "nl", "polish": "pl",
}


@register_embed
class CloseLoad:
    id = "closeload"
    name = "CloseLoad"
    rank = 106

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        html = await fetcher.get(url, headers={"Referer": REFERER})
        # Extract captions from <track> elements
        captions = []
        for src, label in TRACK_RE.findall(html):
            if "thumbnails" in label.lower():
                continue
            lang = LANG_MAP.get(label.lower().strip(), label[:2].lower() if label else "en")
            fmt = "vtt" if src.endswith(".vtt") else "srt"
            captions.append(Caption(url=src, lang=lang, format=fmt))

        # Extract stream from packed JS
        if unpacker.detect(html):
            unpacked = unpacker.unpack(html)
            m = FILE_RE.search(unpacked)
            if m:
                return EmbedResult(streams=[
                    Stream(stream_type="hls", playlist=m.group(1), captions=captions)
                ])

        # Fallback: direct regex
        m = FILE_RE.search(html)
        if m:
            return EmbedResult(streams=[
                Stream(stream_type="hls", playlist=m.group(1), captions=captions)
            ])
        raise Exception("CloseLoad stream not found")
