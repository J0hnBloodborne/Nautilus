"""
Filemoon embed scraper.
Uses packed JS deobfuscation → extracts HLS URL + optional subtitles.
"""
from __future__ import annotations
import re
from urllib.parse import urlparse, parse_qs
from ..base import EmbedResult, Stream, Caption
from ..fetcher import Fetcher
from ..runner import register_embed
from .. import unpacker

PACKED_RE = re.compile(r'(eval\(function\(p,a,c,k,e,d\).*?\)\)\))', re.DOTALL)
FILE_RE = re.compile(r'file:"([^"]+)"')

# Language label → ISO code
LANG_MAP = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "portuguese": "pt", "russian": "ru", "japanese": "ja",
    "korean": "ko", "chinese": "zh", "arabic": "ar", "hindi": "hi",
    "turkish": "tr", "dutch": "nl", "polish": "pl", "swedish": "sv",
}


@register_embed
class FilemoonEmbed:
    id = "filemoon"
    name = "Filemoon"
    rank = 400

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        html = await fetcher.get(url)
        packed = PACKED_RE.search(html)
        if not packed:
            raise ValueError("Filemoon packed JS not found")

        unpacked = unpacker.unpack(packed.group(1))
        file_match = FILE_RE.search(unpacked)
        if not file_match:
            raise ValueError("Filemoon HLS URL not found")

        playlist = file_match.group(1)

        # Try to extract subtitles from URL params
        captions = []
        parsed = urlparse(url)
        sub_info = parse_qs(parsed.query).get("sub.info", [None])[0]
        if sub_info:
            try:
                subs = await fetcher.get_json(sub_info)
                for sub in (subs if isinstance(subs, list) else []):
                    label = sub.get("label", "")
                    file_url = sub.get("file", "")
                    if not file_url:
                        continue
                    lang = self._label_to_lang(label)
                    fmt = "vtt" if file_url.endswith(".vtt") else "srt"
                    captions.append(Caption(url=file_url, lang=lang, format=fmt))
            except Exception:
                pass

        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=playlist, captions=captions)
        ])

    def _label_to_lang(self, label: str) -> str:
        first = label.lower().split()[0] if label else ""
        return LANG_MAP.get(first, first[:2] if len(first) >= 2 else "en")
