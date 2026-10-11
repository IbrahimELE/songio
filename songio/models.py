"""Podatkovni modeli: pjesma u redu za preuzimanje i njen status."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Status(str, Enum):
    QUEUED = "queued"
    SEARCHING = "searching"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    TAGGING = "tagging"
    DONE = "done"
    EXISTS = "exists"
    ERROR = "error"
    CANCELLED = "cancelled"

    @property
    def is_active(self) -> bool:
        return self in (Status.SEARCHING, Status.DOWNLOADING, Status.CONVERTING, Status.TAGGING)

    @property
    def is_finished(self) -> bool:
        return self in (Status.DONE, Status.EXISTS, Status.ERROR, Status.CANCELLED)

    @property
    def is_indeterminate(self) -> bool:
        return self in (Status.SEARCHING, Status.CONVERTING, Status.TAGGING)


STATUS_LABELS = {
    Status.QUEUED: "U redu čekanja",
    Status.SEARCHING: "Tražim na YouTube-u…",
    Status.DOWNLOADING: "Preuzimam",
    Status.CONVERTING: "Konvertujem u MP3…",
    Status.TAGGING: "Upisujem podatke i omot…",
    Status.DONE: "Gotovo",
    Status.EXISTS: "Već postoji – preskočeno",
    Status.ERROR: "Greška",
    Status.CANCELLED: "Otkazano",
}


@dataclass
class Track:
    source: str  # "youtube" | "spotify"
    url: str  # izvorni link pjesme
    title: str
    artists: list[str] = field(default_factory=list)
    album: str = ""
    album_artist: str = ""
    duration: Optional[int] = None  # sekunde
    cover_url: Optional[str] = None  # mala slika za prikaz u listi
    cover_candidates: list[str] = field(default_factory=list)  # veće slike za omot u MP3
    track_number: Optional[int] = None
    track_total: Optional[int] = None
    disc_number: Optional[int] = None
    year: Optional[str] = None
    genres: list[str] = field(default_factory=list)
    collection: Optional[str] = None  # naziv playliste / albuma
    collection_kind: Optional[str] = None  # "playlist" | "album" | "artist"
    collection_id: Optional[str] = None
    position: Optional[int] = None  # redni broj u playlisti
    total: Optional[int] = None
    spotify_song: Any = None  # spotdl Song objekt (za pretragu na YouTube-u)
    youtube_url: Optional[str] = None  # pronađeni YouTube link (za Spotify pjesme)

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: Status = Status.QUEUED
    progress: float = 0.0
    message: str = ""
    output_path: Optional[str] = None
    error: Optional[str] = None
    cancel: threading.Event = field(default_factory=threading.Event, repr=False, compare=False)

    @property
    def artist(self) -> str:
        names = [a.strip() for a in self.artists if a and a.strip()]
        return ", ".join(names) if names else "Nepoznat izvođač"

    @property
    def display_name(self) -> str:
        return f"{self.artist} - {self.title}"

    @property
    def duration_text(self) -> str:
        if not self.duration:
            return ""
        minutes, seconds = divmod(int(self.duration), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def reset(self) -> None:
        self.status = Status.QUEUED
        self.progress = 0.0
        self.message = ""
        self.error = None
        self.output_path = None
        self.cancel = threading.Event()
