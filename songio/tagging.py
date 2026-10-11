"""Upis ID3 tagova i omota albuma u MP3 fajl."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional

import requests
from mutagen.id3 import APIC, COMM, ID3, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK, WOAS
from mutagen.mp3 import MP3

from .models import Track

log = logging.getLogger(__name__)

USER_AGENT = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Songio/1.0"}


def fetch_bytes(url: str, timeout: int = 20) -> Optional[bytes]:
    try:
        resp = requests.get(url, timeout=timeout, headers=USER_AGENT)
        if resp.ok and resp.content and len(resp.content) > 1000:
            return resp.content
    except Exception as exc:
        log.debug("Ne mogu preuzeti sliku %s: %s", url, exc)
    return None


def to_square_jpeg(data: bytes, max_size: int = 1000) -> bytes:
    """Izreži sliku na kvadrat (YouTube sličice su 16:9) i spremi kao JPEG."""
    try:
        from PIL import Image
    except ImportError:
        return data
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        width, height = image.size
        side = min(width, height)
        if width != height:
            left = (width - side) // 2
            top = (height - side) // 2
            image = image.crop((left, top, left + side, top + side))
        if side > max_size:
            image = image.resize((max_size, max_size), Image.LANCZOS)
        if image.mode != "RGB":
            image = image.convert("RGB")
        out = io.BytesIO()
        image.save(out, "JPEG", quality=90)
        return out.getvalue()
    except Exception as exc:
        log.debug("Obrada omota nije uspjela: %s", exc)
        return data


def fetch_cover(track: Track) -> Optional[bytes]:
    """Preuzmi najbolji dostupni omot za pjesmu (ili None)."""
    urls = list(track.cover_candidates)
    if track.cover_url and track.cover_url not in urls:
        urls.append(track.cover_url)
    for url in urls[:6]:
        data = fetch_bytes(url)
        if data:
            return to_square_jpeg(data) if track.source == "youtube" else data
    return None


def _mime(data: bytes) -> str:
    return "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def write_tags(path: Path, track: Track, cover: Optional[bytes]) -> None:
    """Upiši naslov, izvođača, album, godinu, broj pjesme i omot u MP3."""
    audio = MP3(str(path))
    if audio.tags is None:
        audio.add_tags()
    tags: ID3 = audio.tags  # type: ignore[assignment]
    for key in list(tags.keys()):
        del tags[key]

    tags.add(TIT2(encoding=3, text=track.title))
    tags.add(TPE1(encoding=3, text=track.artist))
    if track.album:
        tags.add(TALB(encoding=3, text=track.album))
    album_artist = track.album_artist or (track.artists[0] if track.artists else "")
    if album_artist:
        tags.add(TPE2(encoding=3, text=album_artist))
    if track.track_number:
        text = f"{track.track_number}/{track.track_total}" if track.track_total else str(track.track_number)
        tags.add(TRCK(encoding=3, text=text))
    if track.disc_number:
        tags.add(TPOS(encoding=3, text=str(track.disc_number)))
    if track.year:
        tags.add(TDRC(encoding=3, text=str(track.year)))
    genres = [g for g in track.genres if g and g.strip()]
    if genres:
        tags.add(TCON(encoding=3, text=", ".join(genres)))
    tags.add(COMM(encoding=3, lang="eng", desc="", text=f"Songio · {track.url}"))
    tags.add(WOAS(url=track.url))
    if cover:
        tags.add(APIC(encoding=3, mime=_mime(cover), type=3, desc="Cover", data=cover))
    audio.save(v2_version=3)
