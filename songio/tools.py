"""Pronalaženje i automatsko preuzimanje vanjskih alata: ffmpeg i JavaScript runtime (Deno ili Node)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
from typing import Callable, Optional

import requests

from .paths import app_dir, bin_dir

log = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
ProgressFn = Callable[[int, int], None]  # (preuzeto bajtova, ukupno bajtova ili 0)

FFMPEG_URLS = [
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
]
DENO_LATEST_URL = "https://dl.deno.land/release-latest.txt"
DENO_ZIP_URL = "https://dl.deno.land/release/{version}/deno-x86_64-pc-windows-msvc.zip"
USER_AGENT = {"User-Agent": "Songio/1.0"}


class ToolError(Exception):
    """Greška pri pronalaženju ili preuzimanju alata."""


def _exe(name: str) -> str:
    return name + (".exe" if sys.platform == "win32" else "")


def _runs(path: Path, args: tuple[str, ...] = ("-version",)) -> bool:
    try:
        result = subprocess.run(
            [str(path), *args],
            capture_output=True,
            timeout=20,
            creationflags=CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    except Exception:
        return False


def find_ffmpeg(override: str = "") -> Optional[Path]:
    """Vrati putanju do ispravnog ffmpeg.exe ili None."""
    candidates: list[Path] = []
    if override:
        p = Path(override)
        candidates.append(p / _exe("ffmpeg") if p.is_dir() else p)
    candidates += [
        bin_dir() / _exe("ffmpeg"),
        app_dir() / "bin" / _exe("ffmpeg"),
        app_dir() / _exe("ffmpeg"),
    ]
    found = shutil.which("ffmpeg")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file() and _runs(candidate):
            return candidate
    return None


def find_js_runtime(override: str = "") -> Optional[tuple[str, Path]]:
    """Vrati (ime, putanja) JavaScript runtime-a koji yt-dlp može koristiti (deno ili node)."""
    candidates: list[tuple[str, Path]] = []
    if override:
        p = Path(override)
        if p.is_dir():
            candidates += [(name, p / _exe(name)) for name in ("deno", "node")]
        else:
            candidates.append(("node" if "node" in p.name.lower() else "deno", p))
    candidates += [
        ("deno", bin_dir() / _exe("deno")),
        ("deno", app_dir() / "bin" / _exe("deno")),
    ]
    for name in ("deno", "node"):
        found = shutil.which(name)
        if found:
            candidates.append((name, Path(found)))
    candidates.append(("deno", Path.home() / ".deno" / "bin" / _exe("deno")))
    for base in (
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    ):
        if base:
            candidates.append(("node", Path(base) / "nodejs" / "node.exe"))
    for name, path in candidates:
        if path.is_file() and _runs(path, ("--version",)):
            return name, path
    return None


def yt_dlp_runtime_params(runtime: Optional[tuple[str, Path]]) -> dict:
    """Parametri za yt-dlp koji mu kažu koji JS runtime da koristi."""
    if not runtime:
        return {}
    name, path = runtime
    return {"js_runtimes": {name: {"path": str(path)}}}


def download_file(
    url: str,
    dest: Path,
    progress: Optional[ProgressFn] = None,
    cancel: Optional[threading.Event] = None,
) -> None:
    part = dest.with_name(dest.name + ".part")
    with requests.get(url, stream=True, timeout=(15, 60), headers=USER_AGENT, allow_redirects=True) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(part, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=256 * 1024):
                if cancel is not None and cancel.is_set():
                    raise ToolError("Preuzimanje otkazano.")
                if chunk:
                    fh.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    part.replace(dest)


def _extract_members(zip_path: Path, wanted: set[str], target_dir: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            base = Path(info.filename).name.lower()
            if base in wanted and base not in found:
                out = target_dir / base
                with archive.open(info) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                found[base] = out
    return found


def download_ffmpeg(
    progress: Optional[ProgressFn] = None, cancel: Optional[threading.Event] = None
) -> Path:
    """Preuzmi ffmpeg (Windows build) u folder aplikacije i vrati putanju do ffmpeg.exe."""
    if sys.platform != "win32":
        raise ToolError("Automatsko preuzimanje ffmpeg-a je podržano samo na Windowsu.")
    target = bin_dir()
    zip_path = target / "ffmpeg.zip"
    last_error: Optional[Exception] = None
    for url in FFMPEG_URLS:
        try:
            log.info("Preuzimam ffmpeg: %s", url)
            download_file(url, zip_path, progress, cancel)
            last_error = None
            break
        except ToolError:
            raise
        except Exception as exc:
            last_error = exc
            log.warning("Izvor za ffmpeg nije uspio (%s): %s", url, exc)
    if last_error is not None:
        raise ToolError(f"Preuzimanje ffmpeg-a nije uspjelo: {last_error}")
    try:
        found = _extract_members(zip_path, {"ffmpeg.exe", "ffprobe.exe"}, target)
    finally:
        zip_path.unlink(missing_ok=True)
    if "ffmpeg.exe" not in found:
        raise ToolError("U preuzetoj arhivi nema ffmpeg.exe.")
    return found["ffmpeg.exe"]


def download_deno(
    progress: Optional[ProgressFn] = None, cancel: Optional[threading.Event] = None
) -> Path:
    """Preuzmi Deno (JavaScript runtime koji yt-dlp treba za YouTube) i vrati putanju."""
    if sys.platform != "win32":
        raise ToolError("Automatsko preuzimanje Dena je podržano samo na Windowsu.")
    resp = requests.get(DENO_LATEST_URL, timeout=15, headers=USER_AGENT)
    resp.raise_for_status()
    version = resp.text.strip()
    url = DENO_ZIP_URL.format(version=version)
    log.info("Preuzimam Deno %s: %s", version, url)
    target = bin_dir()
    zip_path = target / "deno.zip"
    try:
        download_file(url, zip_path, progress, cancel)
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Preuzimanje Dena nije uspjelo: {exc}") from exc
    try:
        found = _extract_members(zip_path, {"deno.exe"}, target)
    finally:
        zip_path.unlink(missing_ok=True)
    if "deno.exe" not in found:
        raise ToolError("U preuzetoj arhivi nema deno.exe.")
    return found["deno.exe"]
