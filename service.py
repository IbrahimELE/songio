"""Authenticated SONGIO service: enqueue links and report worker progress."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
import zipfile
from pathlib import Path

from web_core import english_message, jobs_dir, links, read, write


ARCHIVE_LIMIT = 90 * 1024 * 1024  # Leave room below the shell's 100 MB export limit.
ARCHIVE_AGE = 24 * 60 * 60


def stored_jobs(root: Path) -> list[dict]:
    jobs = []
    for file in sorted(jobs_dir(root).glob("*.json"), reverse=True):
        try:
            jobs.append(json.loads(file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return jobs


def own_mp3(root: Path, relative: object) -> Path | None:
    """Never put arbitrary paths or symlinks from a job record into an export."""
    if not isinstance(relative, str):
        return None
    parts = Path(relative).parts
    if len(parts) != 3 or parts[:2] != ("songio", "files") or not parts[2].endswith(".mp3"):
        return None
    folder = (root / "songio" / "files").resolve()
    if folder != root.resolve() / "songio" / "files":
        return None
    path = root / relative
    try:
        if path.resolve().parent != folder or not path.is_file():
            return None
    except OSError:
        return None
    return path


def ready_files(root: Path, jobs: list[dict]) -> list[dict]:
    seen = set()
    ready = []
    for job in jobs:
        for item in job.get("items", []):
            relative = item.get("file")
            path = own_mp3(root, relative)
            if path is None or relative in seen:
                continue
            seen.add(relative)
            name = str(item.get("name") or path.name).replace("\\", "/").split("/")[-1]
            name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*').strip(" .")[:160]
            if not name.lower().endswith(".mp3"):
                name = f"{path.stem}.mp3"
            ready.append({"file": relative, "name": name})
    return ready


def archive_dir(root: Path) -> Path:
    folder = root / "songio" / "archives"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def archive_batch(root: Path, body: dict) -> tuple[int, dict]:
    folder = archive_dir(root)
    now = time.time()
    for stale in folder.iterdir():
        if stale.is_file() and now - stale.stat().st_mtime > ARCHIVE_AGE:
            stale.unlink(missing_ok=True)
    batch_id = body.get("batch_id")
    if batch_id is None:
        files = ready_files(root, stored_jobs(root))
        if not files:
            return 400, {"detail": "No MP3s are ready yet."}
        batch_id = uuid.uuid4().hex
        (folder / f"{batch_id}.json").write_text(json.dumps(files, ensure_ascii=False), encoding="utf-8")
        offset = 0
    elif isinstance(batch_id, str) and len(batch_id) == 32 and all(c in "0123456789abcdef" for c in batch_id):
        try:
            files = json.loads((folder / f"{batch_id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 404, {"detail": "This download session has expired. Try Download all again."}
        offset = body.get("offset")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0 or offset >= len(files):
            return 400, {"detail": "Invalid download position."}
    else:
        return 400, {"detail": "Invalid download session."}

    selected = []
    size = 0
    for entry in files[offset:]:
        path = own_mp3(root, entry.get("file"))
        if path is None:
            return 409, {"detail": "A prepared MP3 is no longer available. Try Download all again."}
        length = path.stat().st_size
        # ZIP_STORED adds only a little metadata per file; leave a generous margin.
        if length > ARCHIVE_LIMIT:
            return 413, {"detail": f"{entry['name']} is too large for bulk export. Save it individually."}
        if selected and size + length > ARCHIVE_LIMIT:
            break
        selected.append((entry, path))
        size += length

    archive = folder / f"{batch_id}-{offset}.zip"
    temporary = folder / f".{batch_id}-{offset}-{uuid.uuid4().hex}.tmp"
    try:
        used = set()
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as output:
            for entry, path in selected:
                name = entry["name"]
                if name in used:
                    stem = name[:-4]
                    number = 2
                    while f"{stem} ({number}).mp3" in used:
                        number += 1
                    name = f"{stem} ({number}).mp3"
                used.add(name)
                output.write(path, arcname=name)
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)
    if archive.stat().st_size > 100 * 1024 * 1024:
        archive.unlink(missing_ok=True)
        return 413, {"detail": "This ZIP exceeds the browser's 100 MB export limit. Save tracks individually."}
    next_offset = offset + len(selected)
    return 200, {
        "batch_id": batch_id, "file": archive.relative_to(root).as_posix(),
        "name": "SONGIO-downloads.zip" if next_offset == len(files) and offset == 0 else f"SONGIO-downloads-from-{offset + 1}.zip",
        "count": len(selected), "total": len(files),
        "next_offset": next_offset if next_offset < len(files) else None,
    }


def remove_archive(root: Path, path: str) -> tuple[int, dict]:
    parts = path.split("/")
    batch_id = parts[1] if len(parts) > 1 else ""
    if len(parts) not in (2, 3) or len(batch_id) != 32 or any(c not in "0123456789abcdef" for c in batch_id):
        return 400, {"detail": "Invalid download session."}
    folder = archive_dir(root)
    if len(parts) == 3:
        offset = parts[2]
        if not offset.isascii() or not offset.isdecimal():
            return 400, {"detail": "Invalid archive."}
        (folder / f"{batch_id}-{offset}.zip").unlink(missing_ok=True)
    else:
        (folder / f"{batch_id}.json").unlink(missing_ok=True)
        for archive in folder.glob(f"{batch_id}-*.zip"):
            archive.unlink(missing_ok=True)
    return 200, {"ok": True}


def handle(req: dict, root: Path) -> tuple[int, dict]:
    method, path = req.get("method"), req.get("path", "").strip("/")
    if method == "GET" and path == "jobs":
        items = []
        all_jobs = stored_jobs(root)
        for job in all_jobs[:40]:
            try:
                job["message"] = english_message(job.get("message", ""))
                job["errors"] = [english_message(message) for message in job.get("errors", [])]
                for item in job.get("items", []):
                    item["message"] = english_message(item.get("message", ""))
                items.append(job)
            except (TypeError, ValueError):
                continue
        return 200, {"jobs": items, "ready_count": len(ready_files(root, all_jobs))}
    if method == "POST" and path == "archive":
        body = req.get("body") or {}
        if not isinstance(body, dict):
            return 400, {"detail": "Invalid download request."}
        return archive_batch(root, body)
    if method == "DELETE" and path.startswith("archive/"):
        return remove_archive(root, path)
    if method == "POST" and path == "jobs":
        body = req.get("body") or {}
        if not isinstance(body, dict) or not isinstance(body.get("links"), str):
            return 400, {"detail": "Enter a Spotify or YouTube link."}
        try:
            urls = links(body["links"][:10000])
        except ValueError as exc:
            return 400, {"detail": str(exc)}
        job = {"id": uuid.uuid4().hex[:24], "created": time.time(), "status": "queued",
               "urls": urls, "items": [], "message": "Queued", "errors": []}
        write(root, job)
        return 201, {"job": job}
    return 404, {"detail": "Unknown action."}


if __name__ == "__main__":
    try:
        status, body = handle(json.load(sys.stdin), Path(os.environ["APP_STORAGE_DIR"]))
    except Exception as exc:
        print(f"SONGIO service: {type(exc).__name__}: {exc}", file=sys.stderr)
        status, body = 500, {"detail": "SONGIO is temporarily unavailable."}
    print(json.dumps({"status": status, "body": body}, ensure_ascii=False))
