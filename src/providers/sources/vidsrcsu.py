"""
VidSrcSU — scrapes vidsrc.su for direct HLS playlists.
Parses server lists from the page, picks the highest-ranked one.
"""
from __future__ import annotations
import re
from ..base import MediaContext, SourceResult, Stream, EmbedRef
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://vidsrc.su"


@register_source
class VidSrcSU:
    id = "vidsrcsu"
    name = "VidSrcSU"
    rank = 160
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        if ctx.media_type == "movie":
            url = f"{BASE}/embed/movie/{ctx.tmdb_id}"
        else:
            url = f"{BASE}/embed/tv/{ctx.tmdb_id}/{ctx.season}/{ctx.episode}"

        html = await fetcher.get(url, headers={"Referer": f"{BASE}/"})

        # VidSrcSU embeds server links that point to HLS playlists
        # Look for m3u8 playlists in the page / server responses
        # The page loads servers via AJAX — parse server list
        servers = re.findall(r'data-hash="([^"]+)"', html)
        
        # Try to get direct playlist from each server
        for srv_hash in servers[:3]:  # try top 3
            try:
                srv_url = f"{BASE}/ajax/embed/episode/{srv_hash}/sources"
                srv_data = await fetcher.get_json(srv_url, headers={"Referer": url, "X-Requested-With": "XMLHttpRequest"})
                
                if isinstance(srv_data, dict) and srv_data.get("status") == 200:
                    for src in srv_data.get("result", []):
                        src_id = src.get("id", "")
                        if src_id:
                            src_detail = await fetcher.get_json(
                                f"{BASE}/ajax/embed/source/{src_id}",
                                headers={"Referer": url, "X-Requested-With": "XMLHttpRequest"},
                            )
                            enc_url = src_detail.get("result", {}).get("url", "")
                            if enc_url and ".m3u8" in enc_url:
                                return SourceResult(streams=[
                                    Stream(stream_type="hls", playlist=enc_url)
                                ])
            except Exception:
                continue

        # Fallback: look for direct m3u8 links in the page
        m3u8_matches = re.findall(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
        if m3u8_matches:
            return SourceResult(streams=[
                Stream(stream_type="hls", playlist=m3u8_matches[0])
            ])

        # Fallback: extract iframe embeds and pass to embed scrapers
        iframes = re.findall(r'src="(https?://[^"]+)"', html)
        embeds = []
        for iframe_url in iframes:
            if "filemoon" in iframe_url:
                embeds.append(EmbedRef(embed_id="filemoon", url=iframe_url))
            elif "streamwish" in iframe_url:
                embeds.append(EmbedRef(embed_id="streamwish", url=iframe_url))
            elif "upstream" in iframe_url:
                embeds.append(EmbedRef(embed_id="upstream", url=iframe_url))
            elif "mp4upload" in iframe_url:
                embeds.append(EmbedRef(embed_id="mp4upload", url=iframe_url))

        return SourceResult(embeds=embeds)
