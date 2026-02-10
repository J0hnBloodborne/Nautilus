"""Dood — token-based direct MP4 extraction."""
from __future__ import annotations
import re, time, random, string
from ..base import EmbedResult, Stream, StreamFile
from ..fetcher import Fetcher
from ..runner import register_embed

BASE = "https://d000d.com"


def _nanoid(size=10):
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=size))


@register_embed
class Dood:
    id = "dood"
    name = "Dood"
    rank = 173

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        vid_id = url.split("/d/")[-1].split("/e/")[-1].split("/")[0].split("?")[0]
        html = await fetcher.get(f"{BASE}/e/{vid_id}")

        token_m = re.search(r'\?token=([^&]+)&expiry=', html)
        path_m = re.search(r"\$\.get\('/pass_md5([^']+)", html)
        if not token_m or not path_m:
            raise Exception("Dood token/path not found")

        token = token_m.group(1)
        pass_path = path_m.group(1)

        partial = await fetcher.get(f"{BASE}/pass_md5{pass_path}",
                                    headers={"Referer": f"{BASE}/e/{vid_id}"})
        download_url = f"{partial}{_nanoid()}?token={token}&expiry={int(time.time() * 1000)}"
        if not download_url.startswith("http"):
            raise Exception("Dood invalid URL")

        return EmbedResult(streams=[
            Stream(stream_type="file",
                   qualities=[StreamFile(url=download_url, quality="unknown")],
                   headers={"Referer": f"{BASE}/"})
        ])
