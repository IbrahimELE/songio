"""Small, file-backed handoff between SONGIO's short service calls and worker."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from songio.sources import classify, extract_links

ID = re.compile(r"^[0-9a-f]{24}$")

_WEB_MESSAGES = {
    "Čitam linkove…": "Reading links…",
    "U redu čekanja": "Queued",
    "Gotovo": "Complete",
    "Preuzimanje nije uspjelo": "Download failed",
    "Povezujem se…": "Connecting…",
    "Pjesma nije pronađena na YouTube-u.": "Track not found on YouTube.",
    "MP3 fajl nije nastao (provjeri ffmpeg).": "MP3 creation failed. Check FFmpeg.",
    "Traženi audio format nije dostupan.": "The requested audio format is unavailable.",
    "Video nije dostupan.": "This video is unavailable.",
    "Video je privatan.": "This video is private.",
    "Video je uklonjen.": "This video has been removed.",
    "Link nije ispravan.": "Invalid link.",
    "Nepoznata greška.": "Unknown error.",
    "YouTube nije vratio podatke za ovaj link.": "YouTube returned no details for this link.",
    "Playlista je prazna ili nedostupna.": "This playlist is empty or unavailable.",
    "Spotify nije vratio nijednu pjesmu za ovaj link.": "Spotify returned no tracks for this link.",
    "Skraćeni Spotify link ne vodi na pjesmu, album ni playlistu.": "This short Spotify link does not lead to a track, album, or playlist.",
    "YouTube privremeno ograničava zahtjeve (429). Pokušaj kasnije.": "YouTube is temporarily rate-limiting requests (429). Try again later.",
    "YouTube je odbio zahtjev (403). Pokušaj ponovo ili uključi kolačiće.": "YouTube rejected the request (403). Try again later.",
    "Ne mogu se povezati (provjeri internet vezu).": "Could not connect. Check your internet connection.",
    "Nedostaje JavaScript runtime (Deno). Preuzmi ga u postavkama.": "The required JavaScript runtime is unavailable.",
}


def english_message(message: str) -> str:
    """Present web-job messages in English without changing desktop errors or saved jobs."""
    if not message:
        return ""
    if "U postavkama uključi kolačiće iz browsera" in message:
        return "YouTube requires sign-in or a bot check. Browser cookies are not yet supported in this web edition."
    for source, target in (
        ("YouTube greška: ", "YouTube error: "),
        ("Ne mogu otvoriti skraćeni Spotify link: ", "Could not open the short Spotify link: "),
        ("Spotify klijent nije spreman: ", "Spotify is unavailable: "),
    ):
        if message.startswith(source):
            return target + english_message(message[len(source):])
    return re.sub(r"\bjoš\s+", "ETA ", _WEB_MESSAGES.get(message, message))


def jobs_dir(root: Path) -> Path:
    path = root / "songio" / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def read(root: Path, ident: str) -> dict:
    if not ID.fullmatch(ident):
        raise ValueError("Invalid job.")
    return json.loads((jobs_dir(root) / f"{ident}.json").read_text(encoding="utf-8"))


def write(root: Path, job: dict) -> None:
    path = jobs_dir(root) / f"{job['id']}.json"
    fd, temp = tempfile.mkstemp(prefix=".songio-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(job, stream, ensure_ascii=False)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def links(value: str) -> list[str]:
    raw = extract_links(value)
    if not raw:
        raw = [line.strip() for line in value.splitlines() if line.strip()]
    if not raw or len(raw) > 20:
        raise ValueError("Enter 1–20 Spotify or YouTube links.")
    result = []
    for item in raw:
        info = classify(item)
        if not info.supported:
            raise ValueError(f"Unsupported link: {item[:90]}")
        result.append(info.url)
    return result
