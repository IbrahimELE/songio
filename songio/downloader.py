"""Preuzimanje jedne pjesme: pretraga (za Spotify), yt-dlp preuzimanje, konverzija u MP3, tagovi."""

from __future__ import annotations

import logging
import re
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .models import Status, Track
from .settings import Settings
from .sources import YdlLogger, apply_full_metadata, friendly_error
from .tagging import fetch_cover, write_tags

log = logging.getLogger(__name__)


class DownloadCancelled(Exception):
    """Korisnik je otkazao preuzimanje."""


class DownloadFailed(Exception):
    """Preuzimanje nije uspjelo; poruka je namijenjena korisniku."""


Reporter = Callable[[Status, float, str], None]


@dataclass
class Context:
    settings: Settings
    ffmpeg: Path
    ydl_extra: dict
    tmp: Path


_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name: str, limit: int = 120) -> str:
    """Ime fajla bez znakova koje Windows ne dopušta."""
    cleaned = _INVALID.sub("", name or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if len(cleaned) > limit:
        cleaned = cleaned[:limit].rstrip(" .")
    return cleaned or "pjesma"


def fmt_size(value: float) -> str:
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def fmt_eta(seconds) -> str:
    if seconds is None:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


def target_path(track: Track, settings: Settings) -> Path:
    """Konačna putanja MP3 fajla prema postavkama (folder, podfolder playliste, obrazac imena)."""
    folder = Path(settings.output_dir)
    if settings.playlist_subfolder and track.collection:
        folder = folder / safe_name(track.collection, 80)
    name = settings.filename_pattern.format(artist=track.artist, title=track.title)
    if settings.number_tracks and track.position:
        name = f"{track.position:02d} - {name}"
    return folder / (safe_name(name) + ".mp3")


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for i in range(2, 1000):
        candidate = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not candidate.exists():
            return candidate
    return path


# --------------------------------------------------------------- YouTube Music pretraga

_local = threading.local()


def _ytm_provider():
    """spotdl YouTube Music provider, po jedan po niti; engleski jezik jer 'songs' filter s njemačkim vraća prazno."""
    provider = getattr(_local, "ytm", None)
    if provider is None:
        from spotdl.providers.audio.ytmusic import YouTubeMusic
        from spotdl.utils.matching import get_best_matches
        from ytmusicapi import YTMusic

        class FastYouTubeMusic(YouTubeMusic):
            GET_RESULTS_OPTS = [
                {"filter": "songs", "ignore_spelling": True, "limit": 20},
                {"filter": "videos", "ignore_spelling": True, "limit": 20},
            ]

            @staticmethod
            def _create_client() -> YTMusic:
                return YTMusic(language="en")

            def get_best_result(self, results):
                # bez dohvaćanja broja pregleda za svaki rezultat (to traje desetke sekundi)
                best = get_best_matches(results, 8)
                return best[0][0], best[0][1]

        provider = FastYouTubeMusic(output_format="mp3")
        _local.ytm = provider
    return provider


def _ytsearch_fallback(track: Track, ydl_extra: dict) -> Optional[str]:
    from yt_dlp import YoutubeDL

    query = f"{track.artist} - {track.title}"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": YdlLogger(),
        "extract_flat": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 30,
        **ydl_extra,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
    except Exception as exc:
        log.warning("YouTube pretraga nije uspjela za %s: %s", query, exc)
        return None
    entries = [e for e in ((info or {}).get("entries") or []) if e and e.get("id")]
    if not entries:
        return None
    best = entries[0]
    if track.duration:
        for entry in entries:
            duration = entry.get("duration")
            if duration and abs(duration - track.duration) <= max(10, track.duration * 0.12):
                best = entry
                break
    return f"https://www.youtube.com/watch?v={best['id']}"


def resolve_youtube_url(track: Track, ydl_extra: dict) -> str:
    """Pronađi YouTube link za Spotify pjesmu (YouTube Music pretraga, pa obična YouTube pretraga)."""
    url: Optional[str] = None
    if track.spotify_song is not None:
        try:
            url = _ytm_provider().search(track.spotify_song)
        except Exception as exc:
            log.warning("YouTube Music pretraga nije uspjela za %s: %s", track.display_name, exc)
    if not url:
        url = _ytsearch_fallback(track, ydl_extra)
    if not url:
        raise DownloadFailed("Pjesma nije pronađena na YouTube-u.")
    log.info("%s -> %s", track.display_name, url)
    return url


# --------------------------------------------------------------- glavni tok


def _cleanup(tmp: Path, track_id: str) -> None:
    for leftover in tmp.glob(f"{track_id}*"):
        try:
            leftover.unlink()
        except OSError:
            pass


def _find_output(info: Optional[dict], tmp: Path, track_id: str) -> Optional[Path]:
    expected = tmp / f"{track_id}.mp3"
    if expected.exists():
        return expected
    for item in (info or {}).get("requested_downloads") or []:
        path = item.get("filepath")
        if path and Path(path).exists():
            return Path(path)
    path = (info or {}).get("filepath")
    if path and Path(path).exists():
        return Path(path)
    matches = sorted(tmp.glob(f"{track_id}*.mp3"))
    return matches[0] if matches else None


def download_track(track: Track, ctx: Context, report: Reporter) -> Path:
    """Preuzmi pjesmu i vrati konačnu putanju. Baca DownloadCancelled ili DownloadFailed."""
    settings = ctx.settings
    final = target_path(track, settings)
    if settings.skip_existing and final.exists():
        track.output_path = str(final)
        report(Status.EXISTS, 100.0, "")
        return final
    if track.cancel.is_set():
        raise DownloadCancelled()

    if track.source == "spotify":
        if not track.youtube_url:
            report(Status.SEARCHING, 0.0, "")
            track.youtube_url = resolve_youtube_url(track, ctx.ydl_extra)
        source_url = track.youtube_url
    else:
        source_url = track.url
    if track.cancel.is_set():
        raise DownloadCancelled()

    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadCancelled as YdlCancelled
    from yt_dlp.utils import DownloadError as YdlDownloadError

    last_report = {"t": 0.0}

    def hook(data: dict) -> None:
        if track.cancel.is_set():
            raise YdlCancelled("Otkazano")
        status = data.get("status")
        if status == "downloading":
            now = time.monotonic()
            if now - last_report["t"] < 0.15:
                return
            last_report["t"] = now
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            pct = (done / total * 100.0) if total else 0.0
            bits = [f"{fmt_size(done)} / {fmt_size(total)}" if total else fmt_size(done)]
            if data.get("speed"):
                bits.append(f"{fmt_size(data['speed'])}/s")
            if data.get("eta") is not None:
                bits.append(f"još {fmt_eta(data['eta'])}")
            report(Status.DOWNLOADING, pct, " · ".join(bits))
        elif status == "finished":
            report(Status.CONVERTING, 100.0, "")

    def pp_hook(data: dict) -> None:
        if track.cancel.is_set():
            raise YdlCancelled("Otkazano")
        if data.get("status") == "started" and "ExtractAudio" in str(data.get("postprocessor", "")):
            report(Status.CONVERTING, 100.0, "")

    opts = {
        "format": "bestaudio/best",
        "outtmpl": {"default": str(ctx.tmp / f"{track.id}.%(ext)s")},
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": settings.bitrate}
        ],
        "ffmpeg_location": str(ctx.ffmpeg),
        "progress_hooks": [hook],
        "postprocessor_hooks": [pp_hook],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": YdlLogger(),
        "noplaylist": True,
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "overwrites": True,
        "windowsfilenames": True,
        "keepvideo": False,
        **ctx.ydl_extra,
    }
    if settings.cookies_browser:
        opts["cookiesfrombrowser"] = (settings.cookies_browser,)

    report(Status.DOWNLOADING, 0.0, "Povezujem se…")
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(source_url, download=True)
    except YdlCancelled as exc:
        _cleanup(ctx.tmp, track.id)
        raise DownloadCancelled() from exc
    except YdlDownloadError as exc:
        _cleanup(ctx.tmp, track.id)
        if track.cancel.is_set():
            raise DownloadCancelled() from exc
        raise DownloadFailed(friendly_error(exc)) from exc
    except Exception as exc:
        _cleanup(ctx.tmp, track.id)
        if track.cancel.is_set():
            raise DownloadCancelled() from exc
        log.exception("Neočekivana greška pri preuzimanju %s", track.display_name)
        raise DownloadFailed(friendly_error(exc)) from exc

    if track.cancel.is_set():
        _cleanup(ctx.tmp, track.id)
        raise DownloadCancelled()

    if info and info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        info = entries[0] if entries else info

    mp3 = _find_output(info, ctx.tmp, track.id)
    if mp3 is None:
        _cleanup(ctx.tmp, track.id)
        raise DownloadFailed("MP3 fajl nije nastao (provjeri ffmpeg).")

    if track.source == "youtube" and info:
        try:
            apply_full_metadata(track, info)
        except Exception as exc:
            log.debug("Metapodaci nisu osvježeni: %s", exc)
        final = target_path(track, settings)

    report(Status.TAGGING, 100.0, "")
    cover = fetch_cover(track) if settings.embed_cover else None
    try:
        write_tags(mp3, track, cover)
    except Exception as exc:
        log.warning("Tagovi nisu upisani za %s: %s", track.display_name, exc)

    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists():
        if settings.skip_existing:
            _cleanup(ctx.tmp, track.id)
            track.output_path = str(final)
            report(Status.EXISTS, 100.0, "")
            return final
        final = unique_path(final)
    shutil.move(str(mp3), str(final))
    _cleanup(ctx.tmp, track.id)
    track.output_path = str(final)
    report(Status.DONE, 100.0, "")
    return final
