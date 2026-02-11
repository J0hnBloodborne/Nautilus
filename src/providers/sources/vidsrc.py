"""
VidSrc — resolves vidsrcme.ru → cloudnestra.com prorcp → HLS streams.

Flow:
  1. vidsrcme.ru/embed/{type}/{tmdb_id}/  → HTML with data-hash attributes
  2. cloudnestra.com/rcp/{hash}           → HTML with prorcp sub-iframe
  3. cloudnestra.com/prorcp/{sub_hash}    → M3U8 URLs with {v1} template domains
  4. Replace {v1}→cloudnestra.com         → Working HLS manifest on tmstr2.cloudnestra.com

Coverage: ~27% of popular movies (those with prorcp sources).
Resolution: Up to 1920x800 (1080p).
"""
from __future__ import annotations
import re
import base64
import logging

from ..base import MediaContext, SourceResult, Stream, Caption
from ..fetcher import Fetcher
from ..runner import register_source

log = logging.getLogger("nautilus.providers.vidsrc")

VIDSRC = "https://vidsrcme.ru"
CLOUDNESTRA = "https://cloudnestra.com"


@register_source
class VidSrc:
    id = "vidsrc"
    name = "VidSrc"
    rank = 350                            # below MoviesAPI (400) as fallback
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        # ── Step 1: get data-hash values from vidsrcme.ru ──
        if ctx.media_type == "movie":
            embed_url = f"{VIDSRC}/embed/movie/{ctx.tmdb_id}/"
        else:
            embed_url = f"{VIDSRC}/embed/tv/{ctx.tmdb_id}/{ctx.season}/{ctx.episode}/"

        log.info("[vidsrc] fetching %s", embed_url)
        html = await fetcher.get(embed_url, headers={"Referer": f"{VIDSRC}/"})

        hashes = re.findall(r'data-hash="([^"]+)"', html)
        if not hashes:
            log.warning("[vidsrc] no data-hash found")
            return SourceResult()

        log.info("[vidsrc] found %d hashes", len(hashes))

        # ── Step 2: try each hash until we get a working prorcp ──
        for hash_idx, source_hash in enumerate(hashes):
            stream = await self._try_hash(source_hash, embed_url, fetcher)
            if stream:
                return SourceResult(streams=[stream])

        log.warning("[vidsrc] no prorcp streams found from any hash")
        return SourceResult()

    async def _try_hash(self, source_hash: str, referer: str, fetcher: Fetcher) -> Stream | None:
        """Try to resolve a single data-hash → M3U8 stream."""
        rcp_url = f"{CLOUDNESTRA}/rcp/{source_hash}"

        try:
            rcp_html = await fetcher.get(rcp_url, headers={"Referer": referer})
        except Exception as e:
            log.debug("[vidsrc] rcp fetch failed: %s", e)
            return None

        # Look for prorcp sub-iframe
        prorcp_matches = re.findall(r'/prorcp/([A-Za-z0-9+/=_-]+)', rcp_html)
        if not prorcp_matches:
            log.debug("[vidsrc] no prorcp in rcp page")
            return None

        prorcp_hash = prorcp_matches[0]
        prorcp_url = f"{CLOUDNESTRA}/prorcp/{prorcp_hash}"

        log.info("[vidsrc] following prorcp: %s", prorcp_url[:80])

        try:
            prorcp_html = await fetcher.get(
                prorcp_url,
                headers={"Referer": rcp_url},
            )
        except Exception as e:
            log.debug("[vidsrc] prorcp fetch failed: %s", e)
            return None

        # ── Step 3: extract M3U8 URLs ──
        m3u8_urls = re.findall(
            r"(https?://[^\s\"']+\.m3u8[^\s\"']*)", prorcp_html
        )
        if not m3u8_urls:
            log.warning("[vidsrc] no M3U8 URLs in prorcp page")
            return None

        # Replace domain template {v1} → cloudnestra.com
        hls_url = m3u8_urls[0].replace("{v1}", "cloudnestra.com")
        log.info("[vidsrc] resolved HLS: %s", hls_url[:120])

        # ── Step 4: extract subtitles ──
        captions = self._extract_captions(prorcp_html)

        # ── Step 5: extract filename for logging ──
        filename = self._extract_filename(prorcp_html)
        if filename:
            log.info("[vidsrc] file: %s", filename[:80])

        return Stream(
            stream_type="hls",
            playlist=hls_url,
            captions=captions,
            headers={
                "Referer": f"{CLOUDNESTRA}/",
                "Origin": CLOUDNESTRA,
            },
        )

    def _extract_captions(self, html: str) -> list[Caption]:
        """Extract subtitle VTT files from prorcp page JS."""
        captions = []

        # Pattern 1: ds_langs array with language objects
        lang_blocks = re.findall(
            r'\{[^}]*?["\'](?:src|file|url)["\']:\s*["\']'
            r'(https?://[^\s"\']+\.vtt[^\s"\']*)["\']'
            r'[^}]*?["\'](?:label|srclang|lang)["\']:\s*["\']([^"\']+)["\']'
            r'[^}]*?\}',
            html,
        )
        for vtt_url, label in lang_blocks:
            if "sli" in vtt_url or "thumb" in label.lower():
                continue
            lang = _label_to_lang(label)
            captions.append(Caption(url=vtt_url, lang=lang, format="vtt"))

        # Pattern 2: simple VTT URL list
        if not captions:
            vtt_urls = re.findall(
                r'(https?://[^\s"\']+\.vtt[^\s"\']*)', html
            )
            for vtt_url in vtt_urls:
                if "sli" in vtt_url or "thumb" in vtt_url:
                    continue
                lang_match = re.search(r'[_.]([a-z]{2})\.vtt', vtt_url)
                lang = lang_match.group(1) if lang_match else "en"
                captions.append(Caption(url=vtt_url, lang=lang, format="vtt"))

        return captions

    def _extract_filename(self, html: str) -> str | None:
        """Extract the base64-encoded filename from the prorcp page."""
        match = re.search(r"atob\('([A-Za-z0-9+/=]+)'\)", html)
        if match:
            try:
                return base64.b64decode(match.group(1)).decode("utf-8", errors="replace")
            except Exception:
                pass
        return None


# ── Utility ──────────────────────────────────────────────

_LANG_MAP = {
    "english": "en", "spanish": "es", "portuguese": "pt",
    "french": "fr", "german": "de", "italian": "it",
    "dutch": "nl", "russian": "ru", "japanese": "ja",
    "korean": "ko", "chinese": "zh", "arabic": "ar",
    "turkish": "tr", "greek": "el", "czech": "cs",
    "danish": "da", "finnish": "fi", "norwegian": "no",
    "swedish": "sv", "hungarian": "hu", "polish": "pl",
    "romanian": "ro", "croatian": "hr", "slovenian": "sl",
    "bulgarian": "bg", "serbian": "sr", "hebrew": "he",
    "thai": "th", "indonesian": "id", "malay": "ms",
    "vietnamese": "vi", "hindi": "hi", "bengali": "bn",
}


def _label_to_lang(label: str) -> str:
    """Convert subtitle label like 'English' to ISO 639-1 code."""
    lower = label.strip().lower()
    return _LANG_MAP.get(lower, lower[:2])
