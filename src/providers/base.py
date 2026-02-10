"""
Core types for the Nautilus provider system.

Two stream types:
  - HLS: m3u8 playlist URL → feed to HLS.js
  - File: direct mp4 URL(s) with quality labels
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

# ──────────────────────────────
#  Caption / Subtitle
# ──────────────────────────────
@dataclass
class Caption:
    url: str
    lang: str                         # ISO 639-1 code e.g. "en"
    format: str = "srt"               # "srt" | "vtt"

    def to_dict(self):
        return {"url": self.url, "lang": self.lang, "format": self.format}

# ──────────────────────────────
#  Stream definitions
# ──────────────────────────────
@dataclass
class StreamFile:
    url: str
    quality: str = "unknown"          # "360" | "480" | "720" | "1080" | "4k" | "unknown"

    def to_dict(self):
        return {"url": self.url, "quality": self.quality}

@dataclass
class Stream:
    stream_type: str                  # "hls" | "file"
    # HLS fields
    playlist: Optional[str] = None    # m3u8 URL (for type=hls)
    # File fields
    qualities: list[StreamFile] = field(default_factory=list)  # (for type=file)
    # Common
    captions: list[Caption] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self):
        d = {"type": self.stream_type, "captions": [c.to_dict() for c in self.captions]}
        if self.headers:
            d["headers"] = self.headers
        if self.stream_type == "hls":
            d["playlist"] = self.playlist
        else:
            d["qualities"] = [q.to_dict() for q in self.qualities]
        return d

# ──────────────────────────────
#  Embed reference (returned by source scrapers)
# ──────────────────────────────
@dataclass
class EmbedRef:
    embed_id: str                     # must match an embed scraper id
    url: str

# ──────────────────────────────
#  Source scraper output
# ──────────────────────────────
@dataclass
class SourceResult:
    embeds: list[EmbedRef] = field(default_factory=list)
    streams: list[Stream] = field(default_factory=list)  # direct streams (skip embed step)

# ──────────────────────────────
#  Embed scraper output
# ──────────────────────────────
@dataclass
class EmbedResult:
    streams: list[Stream] = field(default_factory=list)

# ──────────────────────────────
#  Final run output
# ──────────────────────────────
@dataclass
class RunOutput:
    source_id: str
    embed_id: Optional[str]
    stream: Stream

    def to_dict(self):
        return {
            "source": self.source_id,
            "embed": self.embed_id,
            "stream": self.stream.to_dict(),
        }

# ──────────────────────────────
#  Media context (passed to scrapers)
# ──────────────────────────────
@dataclass
class MediaContext:
    tmdb_id: int
    imdb_id: Optional[str] = None
    title: str = ""
    year: int = 0
    media_type: str = "movie"         # "movie" | "tv"
    season: int = 1
    episode: int = 1
    is_anime: bool = False              # True when genre=Animation + lang=ja
    genres: list[str] = field(default_factory=list)

    def __post_init__(self):
        # Normalize: accept both "show" and "tv" → always "tv"
        if self.media_type == "show":
            self.media_type = "tv"
