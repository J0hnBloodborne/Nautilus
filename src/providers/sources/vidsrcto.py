"""
VidSrcTo — RC4 decryption, emits vidplay + filemoon embeds. Rank 130.
"""
from __future__ import annotations
import re, json, base64
from urllib.parse import urlparse
from ..base import SourceResult, EmbedRef, MediaContext
from ..fetcher import Fetcher
from ..runner import register_source

VIDSRCTO_BASE = "https://vidsrc.to"
DECRYPTION_KEY = "WXrUARXb1aDLaZjI"


def _rc4(key: str, data) -> str:
    """RC4 stream cipher."""
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + ord(key[i % len(key)])) % 256
        state[i], state[j] = state[j], state[i]
    i = j = 0
    result = []
    for idx in range(len(data)):
        i = (i + 1) % 256
        j = (j + state[i]) % 256
        state[i], state[j] = state[j], state[i]
        if isinstance(data[idx], str):
            result.append(chr(ord(data[idx]) ^ state[(state[i] + state[j]) % 256]))
        elif isinstance(data[idx], int):
            result.append(chr(data[idx] ^ state[(state[i] + state[j]) % 256]))
    return "".join(result)


def _decode_b64_url_safe(s: str) -> bytes:
    std = s.replace("_", "/").replace("-", "+")
    return base64.b64decode(std)


def _decrypt_source_url(source_url: str) -> str:
    encoded = _decode_b64_url_safe(source_url)
    decoded = _rc4(DECRYPTION_KEY, encoded)
    from urllib.parse import unquote
    return unquote(unquote(decoded))


@register_source
class VidSrcTo:
    id = "vidsrcto"
    name = "VidSrcTo"
    rank = 250
    media_types = ["movie", "tv"]

    async def scrape(self, ctx: MediaContext, fetcher: Fetcher) -> SourceResult:
        media_id = ctx.imdb_id or str(ctx.tmdb_id)
        if ctx.media_type == "movie":
            url = f"/embed/movie/{media_id}"
        else:
            url = f"/embed/tv/{media_id}/{ctx.season}/{ctx.episode}"

        main_page = await fetcher.get(
            VIDSRCTO_BASE + url,
            headers={"Referer": VIDSRCTO_BASE + "/"},
        )

        # Find data-id
        data_id_m = re.search(r'data-id="([^"]+)"', main_page)
        if not data_id_m:
            raise ValueError("VidSrcTo: no data-id found")

        sources_res = await fetcher.get_json(
            f"{VIDSRCTO_BASE}/ajax/embed/episode/{data_id_m.group(1)}/sources",
            headers={"Referer": VIDSRCTO_BASE + "/"},
        )
        if sources_res.get("status") != 200:
            raise ValueError("VidSrcTo: sources request failed")

        embed_arr = []
        for source in sources_res.get("result", []):
            source_res = await fetcher.get_json(
                f"{VIDSRCTO_BASE}/ajax/embed/source/{source['id']}",
                headers={"Referer": VIDSRCTO_BASE + "/"},
            )
            decrypted = _decrypt_source_url(source_res["result"]["url"])
            embed_arr.append({"source": source["title"], "url": decrypted})

        embeds = []
        for e in embed_arr:
            if e["source"] == "Vidplay":
                embeds.append(EmbedRef(embed_id="vidplay", url=e["url"]))
            elif e["source"] == "Filemoon":
                # Check for subtitles from Vidplay entry
                sub_url = None
                for v in embed_arr:
                    if v["source"] == "Vidplay" and "sub.info" in v["url"]:
                        from urllib.parse import parse_qs, urlparse
                        sub_url = parse_qs(urlparse(v["url"]).query).get("sub.info", [None])[0]
                full_url = e["url"]
                if sub_url:
                    sep = "&" if "?" in full_url else "?"
                    full_url = f"{full_url}{sep}sub.info={sub_url}"
                embeds.append(EmbedRef(embed_id="filemoon", url=full_url))
                embeds.append(EmbedRef(embed_id="filemoon-mp4", url=full_url))

        return SourceResult(embeds=embeds)
