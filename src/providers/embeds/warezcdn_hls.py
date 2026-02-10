"""WarezCDN HLS — decrypts stream ID → cloud.mail.ru videowl HLS. IP_LOCKED."""
from __future__ import annotations
import re, base64
from urllib.parse import urlencode
from ..base import EmbedResult, Stream
from ..fetcher import Fetcher
from ..runner import register_embed
from .warezcdn_common import get_decrypted_id


@register_embed
class WarezCDNHls:
    id = "warezcdnembedhls"
    name = "WarezCDN HLS"
    rank = 83

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        decrypted_id = await get_decrypted_id(url, fetcher)

        # Get videowl URL from cloud.mail.ru share page
        share_page = await fetcher.get("https://cloud.mail.ru/public/uaRH/2PYWcJRpH")
        m = re.search(r'"videowl_view":\{"count":"\d+","url":"([^"]+)"\}', share_page)
        if not m:
            raise ValueError("WarezCDN HLS: videowl URL not found")

        videowl_url = m.group(1)
        encoded_id = base64.b64encode(decrypted_id.encode()).decode()
        stream_url = f"{videowl_url}/0p/{encoded_id}.m3u8?{urlencode({'double_encode': '1'})}"

        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=stream_url)
        ])
