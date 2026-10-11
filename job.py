#!/usr/bin/env python3
"""Supervised, on-demand SONGIO download worker."""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

from songio.downloader import Context, DownloadFailed, download_track
from songio.settings import Settings
from songio.sources import SourceError, analyze_spotify, analyze_youtube, classify
from songio.tools import yt_dlp_runtime_params
from web_core import jobs_dir, read, write


def run_job(root: Path, job: dict) -> None:
    job["status"] = "working"
    job["message"] = "Reading links…"
    write(root, job)
    music = root / "songio" / "music"
    temp = root / "songio" / "tmp"
    temp.mkdir(parents=True, exist_ok=True)
    music.mkdir(parents=True, exist_ok=True)
    from imageio_ffmpeg import get_ffmpeg_exe
    binary = Path(get_ffmpeg_exe())
    ffmpeg = root / "songio" / "bin" / "ffmpeg"
    ffmpeg.parent.mkdir(parents=True, exist_ok=True)
    if not ffmpeg.exists():
        ffmpeg.symlink_to(binary)
    node = shutil.which("node")
    extra = yt_dlp_runtime_params(("node", Path(node))) if node else {}
    settings = Settings(output_dir=str(music), parallel=1)
    ctx = Context(settings=settings, ffmpeg=ffmpeg, ydl_extra=extra, tmp=temp)
    for url in job["urls"]:
        try:
            link = classify(url)
            if link.kind == "youtube_mixed":
                link = classify(link.video_url)
            tracks, _ = (analyze_spotify(link, "", "") if link.is_spotify else analyze_youtube(link, extra))
            if len(tracks) > 500:
                raise SourceError("Playlist too large (500 tracks maximum).")
            for track in tracks:
                item = {"id": track.id, "title": track.title, "artist": track.artist,
                        "status": "queued", "progress": 0, "message": "", "file": None}
                job["items"].append(item)
                write(root, job)

                def report(status, progress, message):
                    item.update(status=status.value, progress=round(progress), message=message)
                    write(root, job)

                try:
                    path = download_track(track, ctx, report)
                    item["name"] = path.name
                    delivered = root / "songio" / "files" / f"{track.id}.mp3"
                    delivered.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), str(delivered))
                    item["file"] = delivered.relative_to(root).as_posix()
                    item["size"] = delivered.stat().st_size
                    item["status"] = "done"
                except Exception as exc:
                    item["status"] = "error"
                    item["message"] = str(exc)[:300]
                write(root, job)
        except Exception as exc:
            job["errors"].append(str(exc)[:300])
            write(root, job)
    job["status"] = "done" if any(i["status"] == "done" for i in job["items"]) else "error"
    job["message"] = "Complete" if job["status"] == "done" else "Download failed"
    write(root, job)


def main() -> None:
    root = Path(os.environ["DATA_DIR"]) / "apps" / sys.argv[1]
    # The supervisor allows one worker at once; new submissions are picked up here.
    while True:
        queued = []
        for file in jobs_dir(root).glob("*.json"):
            try:
                job = read(root, file.stem)
                if job["status"] in ("queued", "working"):
                    queued.append(job)
            except (OSError, ValueError, KeyError):
                continue
        if not queued:
            return
        job = min(queued, key=lambda item: item["created"])
        try:
            run_job(root, job)
        except Exception as exc:
            job["status"], job["message"] = "error", str(exc)[:300]
            write(root, job)


if __name__ == "__main__":
    main()
