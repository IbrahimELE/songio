"""Postavke aplikacije, trajno spremljene u settings.json."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields

from .paths import default_music_dir, settings_file

log = logging.getLogger(__name__)

BITRATES = ["128", "192", "320"]

BROWSERS = [
    ("", "Ne koristi"),
    ("firefox", "Firefox"),
    ("chrome", "Chrome"),
    ("edge", "Edge"),
    ("brave", "Brave"),
    ("opera", "Opera"),
    ("vivaldi", "Vivaldi"),
]

FILENAME_PATTERNS = [
    ("{artist} - {title}", "Izvođač - Naslov"),
    ("{title} - {artist}", "Naslov - Izvođač"),
    ("{title}", "Samo naslov"),
]


@dataclass
class Settings:
    output_dir: str = ""
    bitrate: str = "320"
    parallel: int = 3
    playlist_subfolder: bool = True
    number_tracks: bool = False
    skip_existing: bool = True
    auto_start: bool = True
    embed_cover: bool = True
    filename_pattern: str = "{artist} - {title}"
    cookies_browser: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    ffmpeg_path: str = ""
    js_runtime_path: str = ""
    window_w: int = 0
    window_h: int = 0
    window_x: int = -1
    window_y: int = -1

    def __post_init__(self) -> None:
        if not self.output_dir:
            self.output_dir = str(default_music_dir())
        if self.bitrate not in BITRATES:
            self.bitrate = "320"
        try:
            self.parallel = max(1, min(6, int(self.parallel)))
        except (TypeError, ValueError):
            self.parallel = 3
        if self.filename_pattern not in [pattern for pattern, _ in FILENAME_PATTERNS]:
            self.filename_pattern = "{artist} - {title}"

    @classmethod
    def load(cls) -> "Settings":
        path = settings_file()
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            known = {f.name for f in fields(cls)}
            return cls(**{k: v for k, v in data.items() if k in known})
        except Exception as exc:  # pokvaren fajl ne smije srušiti aplikaciju
            log.warning("Ne mogu učitati postavke (%s), koristim podrazumijevane.", exc)
            return cls()

    def save(self) -> None:
        try:
            settings_file().write_text(
                json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as exc:
            log.warning("Ne mogu spremiti postavke: %s", exc)
