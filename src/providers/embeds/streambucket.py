"""
StreamBucket — hunter (h,u,n,t,e,r) JS deobfuscation → HLS.
Disabled: bot detection issues.
"""
from __future__ import annotations
import re
from ..base import EmbedResult, Stream
from ..fetcher import Fetcher
from ..runner import register_embed

HUNTER_RE = re.compile(
    r'eval\(function\(h,u,n,t,e,r\).*?\("(.*?)",\d*?,"(.*?)",(\d*?),(\d*?),\d*?\)\)',
    re.DOTALL,
)
LINK_RE = re.compile(r'file:"([^"]+)"')


def _decode_hunter(encoded: str, mask: str, char_code_offset: int, delim_offset: int) -> str:
    """Decode hunter-obfuscated string."""
    delimiter = mask[delim_offset]
    chunks = [c for c in encoded.split(delimiter) if c]
    decoded = []
    for chunk in chunks:
        char_code = 0
        for idx, ch in enumerate(reversed(chunk)):
            char_code += mask.index(ch) * (delim_offset ** idx)
        decoded.append(chr(char_code - char_code_offset))
    return "".join(decoded)


@register_embed
class StreamBucketEmbed:
    id = "streambucket"
    name = "StreamBucket"
    rank = 196
    disabled = True

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        html = await fetcher.get(url)

        if "captcha-checkbox" in html:
            raise ValueError("StreamBucket: captcha triggered")

        m = HUNTER_RE.search(html)
        if not m:
            raise ValueError("StreamBucket: hunter JS not found")

        encoded = m.group(1)
        mask = m.group(2)
        char_offset = int(m.group(3))
        delim_offset = int(m.group(4))

        decoded = _decode_hunter(encoded, mask, char_offset, delim_offset)
        link_m = LINK_RE.search(decoded)
        if not link_m:
            raise ValueError("StreamBucket: HLS link not found")

        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=link_m.group(1))
        ])
