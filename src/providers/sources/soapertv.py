"""
SoaperTV — scrapes soapertv.cc for direct HLS streams + subtitles.
One of the best sources: returns HLS playlists with captions.
"""
from __future__ import annotations
import re
import json
from ..base import MediaContext, SourceResult, Stream, Caption
from ..fetcher import Fetcher
from ..runner import register_source

BASE = "https://soaper.live"

# Language code mapping for subtitles
LANG_MAP = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "portuguese": "pt", "russian": "ru", "japanese": "ja",
    "korean": "ko", "chinese": "zh", "arabic": "ar", "hindi": "hi",
    "turkish": "tr", "dutch": "nl", "polish": "pl", "swedish": "sv",
    "norwegian": "no", "danish": "da", "finnish": "fi", "thai": "th",
    "vietnamese": "vi", "indonesian": "id", "czech": "cs", "romanian": "ro",
    "hungarian": "hu", "greek": "el", "hebrew": "he", "malay": "ms",
}


@register_source
class SoaperTV:
    id = "soapertv"
    name = "SoaperTV"
    rank = 200
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # Step 1: Search for the media
        search_html = await fetcher.get(
            f"{BASE}/search.html",
            params={"keyword": ctx.title},
        )

        # Find matching result link
        link = self._find_media_link(search_html, ctx)
        if not link:
            return SourceResult()

        # Step 2: Get the media page
        media_page = await fetcher.get(link, base_url=BASE)

        # Step 3: For shows, find the right episode
        if ctx.media_type == "show":
            ep_link = self._find_episode_link(media_page, ctx.season, ctx.episode)
            if not ep_link:
                return SourceResult()
            media_page = await fetcher.get(ep_link, base_url=BASE)

        # Step 4: Find the pass_url (endpoint to get stream info)
        pass_match = re.search(r'pass_url\s*=\s*["\']([^"\']+)', media_page)
        if not pass_match:
            return SourceResult()

        pass_url = pass_match.group(1)

        # Step 5: Get stream data via POST
        obj_match = re.search(r'<input.*?id=["\']obj["\'].*?value=["\']([^"\']+)', media_page)
        obj_val = obj_match.group(1) if obj_match else ""

        try:
            stream_text = await fetcher.post(
                pass_url,
                base_url=BASE,
                data={"obj": obj_val},
                headers={"Referer": f"{BASE}/", "X-Requested-With": "XMLHttpRequest"},
            )
            stream_data = json.loads(stream_text)
        except Exception:
            return SourceResult()

        # Step 6: Extract stream URL and subtitles
        playlist = stream_data.get("val") or stream_data.get("val_bak")
        if not playlist:
            return SourceResult()

        if not playlist.startswith("http"):
            playlist = f"{BASE}/{playlist.lstrip('/')}"

        captions = []
        for sub in stream_data.get("subs", []):
            name = sub.get("name", "")
            path = sub.get("path", "")
            if not path:
                continue
            lang = self._detect_lang(name)
            sub_url = f"{BASE}{path}" if not path.startswith("http") else path
            captions.append(Caption(url=sub_url, lang=lang, format="srt"))

        return SourceResult(streams=[
            Stream(stream_type="hls", playlist=playlist, captions=captions)
        ])

    def _find_media_link(self, html: str, ctx: MediaContext) -> str | None:
        pattern = r'<a\s+href="(/[^"]+)"[^>]*>\s*<img[^>]*>\s*<div[^>]*>([^<]*)</div>'
        matches = re.findall(pattern, html, re.DOTALL)
        title_lower = ctx.title.lower().strip()
        for href, title in matches:
            if title.strip().lower() == title_lower:
                return href
        # Fuzzy match
        for href, title in matches:
            if title_lower in title.strip().lower():
                return href
        return None

    def _find_episode_link(self, html: str, season: int, episode: int) -> str | None:
        # Look for season/episode links
        pattern = rf'href="(/episode[^"]*s{season}e{episode}[^"]*)"'
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            return m.group(1)
        # Alternative: numbered episode list
        ep_links = re.findall(r'href="(/episode[^"]+)"', html)
        # Try to find by episode number
        for link in ep_links:
            if f"/{episode}" in link or f"-{episode}" in link:
                return link
        return None

    def _detect_lang(self, name: str) -> str:
        name_lower = name.lower().split(".")[0].split(":")[0].strip()
        return LANG_MAP.get(name_lower, name_lower[:2] if len(name_lower) >= 2 else "en")
