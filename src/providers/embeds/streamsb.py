"""
StreamSB — reCAPTCHA bypass + download page parsing → MP4 streams.
Complex: requires solving Google reCAPTCHA v2 invisible.
"""
from __future__ import annotations
import re, base64
from urllib.parse import urlparse
from ..base import EmbedResult, Stream, StreamFile
from ..fetcher import Fetcher
from ..runner import register_embed


async def _fetch_captcha_token(fetcher: Fetcher, domain: str, recaptcha_key: str):
    """Attempt to fetch a reCAPTCHA token (invisible v2)."""
    domain_b64 = base64.b64encode(domain.encode()).decode().replace("=", ".")

    render_js = await fetcher.get(
        "https://www.google.com/recaptcha/api.js",
        params={"render": recaptcha_key},
    )
    v_start = render_js.find("/releases/") + 10
    v_end = render_js.find("/recaptcha__en.js")
    v_token = render_js[v_start:v_end] if v_start > 9 and v_end > 0 else ""

    anchor_html = await fetcher.get(
        "https://www.google.com/recaptcha/api2/anchor",
        params={
            "cb": "1", "hl": "en", "size": "invisible",
            "k": recaptcha_key, "co": domain_b64, "v": v_token,
        },
    )
    c_token_m = re.search(r'id="recaptcha-token"\s+value="([^"]+)"', anchor_html)
    if not c_token_m:
        return None

    token_data = await fetcher.post(
        "https://www.google.com/recaptcha/api2/reload",
        data=None,
        headers={
            "referer": "https://www.google.com/recaptcha/api2/",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    token_m = re.search(r'rresp","(.+?)"', token_data)
    return token_m.group(1) if token_m else None


@register_embed
class StreamSBEmbed:
    id = "streamsb"
    name = "StreamSB"
    rank = 150

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        # Normalize URL
        clean = url.replace(".html", "").replace("embed-", "").replace("e/", "").replace("d/", "")
        parsed = urlparse(clean)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        base_html = await fetcher.get(f"{origin}/d{parsed.path}")

        # Extract download_video() onclick params
        dl_details = []
        for m in re.finditer(
            r"download_video\('([^']+)','([^']+)','([^']+)'\).*?<span[^>]*>([^<]+)",
            base_html, re.DOTALL
        ):
            params = [m.group(1), m.group(2), m.group(3)]
            quality_raw = m.group(4).strip()
            q_match = re.match(r"(.+?)\s*\((.+?)\)", quality_raw)
            if q_match:
                dl_details.append({"params": params, "quality": q_match.group(1).strip()})

        qualities = []
        for dl in dl_details:
            try:
                dl_page = await fetcher.get(
                    f"{origin}/dl",
                    params={
                        "op": "download_orig",
                        "id": dl["params"][0],
                        "mode": dl["params"][1],
                        "hash": dl["params"][2],
                    },
                )
                # Find download link
                link_m = re.search(r'class="btn btn-light btn-lg"[^>]*href="([^"]+)"', dl_page)
                if not link_m:
                    # Try another pattern
                    link_m = re.search(r'href="(https?://[^"]+)"[^>]*class="btn', dl_page)
                if link_m:
                    qualities.append(StreamFile(url=link_m.group(1), quality=dl["quality"]))
            except Exception:
                continue

        if not qualities:
            raise ValueError("StreamSB: no download links found")

        return EmbedResult(streams=[
            Stream(stream_type="file", qualities=qualities)
        ])
