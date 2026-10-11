"""Putanje koje aplikacija koristi (podaci, alati, privremeni fajlovi)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_NAME


def is_frozen() -> bool:
    """True kada aplikacija radi kao PyInstaller .exe."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Folder u kojem se nalazi aplikacija (exe ili izvorni kod)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Folder za podatke aplikacije (LOCALAPPDATA/Songio)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def bin_dir() -> Path:
    """Folder u koji se preuzimaju ffmpeg i deno."""
    path = data_dir() / "bin"
    path.mkdir(parents=True, exist_ok=True)
    return path


def tmp_dir() -> Path:
    """Privremeni folder za fajlove koji se upravo preuzimaju."""
    path = data_dir() / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ui_cache_dir() -> Path:
    path = data_dir() / "ui"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return data_dir() / "settings.json"


def log_file() -> Path:
    return data_dir() / "songio.log"


def default_music_dir() -> Path:
    """Podrazumijevani folder za muziku: ~/Music/Songio."""
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    music = home / "Music"
    if not music.exists():
        music = home
    return music / APP_NAME
