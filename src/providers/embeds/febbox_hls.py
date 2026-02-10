"""
Febbox HLS — showbox share link → febbox file list → HLS.
Disabled: requires showbox which is CF_BLOCKED.
"""
from __future__ import annotations
from ..base import EmbedResult, Stream
from ..fetcher import Fetcher
from ..runner import register_embed
from .febbox_mp4 import _parse_input_url

SHOWBOX_BASE = "https://www.showbox.media"
FEBBOX_BASE = "https://www.febbox.com"


@register_embed
class FebboxHls:
    id = "febbox-hls"
    name = "Febbox (HLS)"
    rank = 160
    disabled = True

    async def scrape(self, url: str, fetcher: Fetcher) -> EmbedResult:
        media_type, mid, season, episode = _parse_input_url(url)

        # Get share link from showbox
        share_res = await fetcher.get_json(
            f"{SHOWBOX_BASE}/index/share_link",
            params={"id": mid, "type": "1" if media_type == "movie" else "2"},
        )
        link = (share_res.get("data") or {}).get("link")
        if not link:
            raise ValueError("Febbox HLS: no share link")

        # Extract share key
        share_key = link.rstrip("/").split("/")[-1]

        # Get file list
        files = await fetcher.get_json(
            f"{FEBBOX_BASE}/file/file_share_list",
            params={"share_key": share_key, "pwd": ""},
            headers={"accept-language": "en"},
        )
        file_list = (files.get("data") or {}).get("file_list", [])

        if media_type == "show":
            # Find season folder
            season_folder = None
            for f in file_list:
                if f.get("is_dir") and f.get("file_name", "").lower() == f"season {season}":
                    season_folder = f
                    break
            if not season_folder:
                raise ValueError("Febbox HLS: season folder not found")

            # Get episodes
            eps = await fetcher.get_json(
                f"{FEBBOX_BASE}/file/file_share_list",
                params={"share_key": share_key, "pwd": "", "parent_id": str(season_folder["fid"]), "page": "1"},
                headers={"accept-language": "en"},
            )
            ep_list = (eps.get("data") or {}).get("file_list", [])
            import re
            pattern = re.compile(rf"[Ss]0*{season}[Ee]0*{episode}")
            file_list = [f for f in ep_list if not f.get("is_dir") and f.get("ext") in ("mp4", "mkv") and pattern.search(f.get("file_name", ""))]
        else:
            file_list = [f for f in file_list if not f.get("is_dir") and f.get("ext") in ("mp4", "mkv")]

        if not file_list:
            raise ValueError("Febbox HLS: no playable stream")

        oss_fid = file_list[0].get("oss_fid")
        playlist = f"https://www.febbox.com/hls/main/{oss_fid}.m3u8"

        return EmbedResult(streams=[
            Stream(stream_type="hls", playlist=playlist)
        ])
