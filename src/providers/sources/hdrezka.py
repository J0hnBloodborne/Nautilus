"""HDRezka — multi-quality direct file streaming."""
from __future__ import annotations
import re, uuid, json
from ..base import SourceResult, Stream, StreamFile, Caption, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://hdrezka.ag"
HEADERS = {
    "X-Hdrezka-Android-App": "1",
    "X-Hdrezka-Android-App-Version": "2.2.0",
}

QUALITY_MAP = {"360p": "360", "480p": "480", "720p": "720", "1080p": "1080", "1080p Ultra": "1080", "2160p": "4k", "2160p Ultra": "4k"}


def _parse_video_links(encoded: str) -> list[StreamFile]:
    """Parse quality→URL pairs from the encoded video string."""
    # Format: [quality]url_or_url
    # URLs are comma-separated with quality tags [720p]url,[1080p]url,...
    # They may also be #2 format: url1 or url2
    files = []
    try:
        # Sometimes links are base64 trailed with $$$ || !! delimiters; strip known junk
        cleaned = encoded
        for junk in ["@", "#h", "!", "$", "^", "//_//", "//^//"]:
            cleaned = cleaned.replace(junk, "")

        # Split by quality tags [qualityp]
        parts = re.split(r'\[(\d+p(?:\s*Ultra)?)\]', cleaned)
        i = 1
        while i < len(parts) - 1:
            quality_label = parts[i]
            url_block = parts[i + 1].split(",")[0].strip()
            # Pick first URL if 'or' separated
            url = url_block.split(" or ")[0].strip()
            if url.startswith("http"):
                q = QUALITY_MAP.get(quality_label, quality_label.replace("p", ""))
                files.append(StreamFile(url=url, quality=q))
            i += 2
    except Exception:
        pass
    return files


def _parse_subtitle_links(encoded: str) -> list[Caption]:
    """Parse subtitle string: [lang]url,..."""
    captions = []
    if not encoded or encoded == "false":
        return captions
    try:
        parts = re.split(r'\[([^\]]+)\]', encoded)
        i = 1
        while i < len(parts) - 1:
            label = parts[i]
            url = parts[i + 1].split(",")[0].strip()
            if url.startswith("http"):
                lang = label.lower()[:2]
                fmt = "vtt" if url.endswith(".vtt") else "srt"
                captions.append(Caption(url=url, lang=lang, format=fmt))
            i += 2
    except Exception:
        pass
    return captions


@register_source
class HDRezka:
    id = "hdrezka"
    name = "HDRezka"
    rank = 140
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # 1. Search
        search_html = await fetcher.get(
            f"{BASE}/engine/ajax/search.php",
            params={"q": ctx.title},
            headers=HEADERS
        )

        # Parse results: <a href="URL"><span class="enty">Title</span> (Year)</a>
        results = re.findall(
            r'<a\s+href="([^"]+)"[^>]*>.*?<span class="enty">([^<]+)</span>\s*\((\d{4})',
            search_html, re.DOTALL
        )
        if not results:
            raise Exception("HDRezka: no search results")

        match_url = None
        for href, title, year in results:
            if str(ctx.year) == year and ctx.title.lower() in title.lower():
                match_url = href
                break
        if not match_url:
            match_url = results[0][0]

        # 2. Get content page
        page = await fetcher.get(match_url, headers=HEADERS)

        # Extract content ID
        id_m = re.search(r'data-id="(\d+)"', page) or re.search(r'/(\d+)-[^/]+\.html', match_url)
        if not id_m:
            raise Exception("HDRezka: content ID not found")
        content_id = id_m.group(1)

        # Get translator IDs
        translator_m = re.search(r'data-translator_id="(\d+)"', page)
        translator_id = translator_m.group(1) if translator_m else "110"

        # 3. Get stream data
        params = {
            "id": content_id,
            "translator_id": translator_id,
            "favs": str(uuid.uuid4()),
            "action": "get_movie" if ctx.media_type == "movie" else "get_stream",
        }
        if ctx.media_type == "tv":
            params["season"] = str(ctx.season or 1)
            params["episode"] = str(ctx.episode or 1)

        stream_data_raw = await fetcher.post(
            f"{BASE}/ajax/get_cdn_series/",
            data=params,
            headers={**HEADERS, "Referer": match_url}
        )
        try:
            stream_data = json.loads(stream_data_raw) if isinstance(stream_data_raw, str) else stream_data_raw
        except Exception:
            raise Exception("HDRezka: stream data parse failed")

        video_url = stream_data.get("url", "")
        subtitle_str = stream_data.get("subtitle", "")

        files = _parse_video_links(video_url)
        captions = _parse_subtitle_links(subtitle_str)

        if not files:
            raise Exception("HDRezka: no video files extracted")

        return SourceResult(
            streams=[
                Stream(stream_type="file", qualities=files, captions=captions,
                       headers={"Referer": f"{BASE}/"})
            ]
        )
