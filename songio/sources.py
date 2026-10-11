"""Prepoznavanje linkova i dohvat popisa pjesama (YouTube preko yt-dlp, Spotify preko spotdl)."""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests

from .models import Track

log = logging.getLogger(__name__)

USER_AGENT = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Songio/1.0"}


class SourceError(Exception):
    """Greška pri analizi linka; poruka je namijenjena korisniku."""


YT_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
SP_HOSTS = {"open.spotify.com", "play.spotify.com", "spotify.link", "spotify.app.link"}

_LINK_RE = re.compile(
    r"(https?://[^\s<>\"'()]+|spotify:(?:track|album|playlist|artist):[A-Za-z0-9]+)", re.I
)


@dataclass
class LinkInfo:
    kind: str  # youtube_video | youtube_playlist | youtube_mixed | spotify_track | spotify_album |
    #            spotify_playlist | spotify_artist | spotify_link | unknown
    url: str
    video_url: str = ""
    playlist_url: str = ""

    @property
    def is_youtube(self) -> bool:
        return self.kind.startswith("youtube")

    @property
    def is_spotify(self) -> bool:
        return self.kind.startswith("spotify")

    @property
    def supported(self) -> bool:
        return self.kind != "unknown"


def extract_links(text: str) -> list[str]:
    """Izvuci sve linkove iz teksta (npr. više linkova zalijepljenih odjednom)."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _LINK_RE.findall(text or ""):
        link = match.rstrip(".,;")
        if link not in seen:
            seen.add(link)
            out.append(link)
    return out


def classify(raw: str) -> LinkInfo:
    """Prepoznaj vrstu linka (YouTube video/playlista, Spotify pjesma/album/playlista)."""
    text = (raw or "").strip()
    match = re.match(r"^spotify:(track|album|playlist|artist):([A-Za-z0-9]+)$", text, re.I)
    if match:
        text = f"https://open.spotify.com/{match.group(1).lower()}/{match.group(2)}"
    if not re.match(r"^https?://", text, re.I):
        text = "https://" + text
    try:
        parts = urlparse(text)
    except ValueError:
        return LinkInfo("unknown", raw)
    host = (parts.hostname or "").lower()
    if host in YT_HOSTS or host.endswith(".youtube.com"):
        return _classify_youtube(parts, raw)
    if host in SP_HOSTS or host.endswith(".spotify.com"):
        return _classify_spotify(parts, host, raw)
    return LinkInfo("unknown", raw)


def _classify_youtube(parts, raw: str) -> LinkInfo:
    query = parse_qs(parts.query)
    path = parts.path or "/"
    segments = [s for s in path.split("/") if s]
    host = (parts.hostname or "").lower()
    video_id: Optional[str] = None
    list_id = (query.get("list") or [None])[0]

    if host in ("youtu.be", "www.youtu.be"):
        video_id = segments[0] if segments else None
    elif path.startswith("/watch"):
        video_id = (query.get("v") or [None])[0]
    elif len(segments) > 1 and segments[0] in ("shorts", "embed", "live", "v"):
        video_id = segments[1]

    if list_id and list_id.startswith("RD"):
        list_id = None  # automatski miksevi su beskonačni – uzmi samo video
    if list_id and (path.startswith("/playlist") or not video_id):
        url = f"https://www.youtube.com/playlist?list={list_id}"
        return LinkInfo("youtube_playlist", url, playlist_url=url)
    if video_id:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        if list_id:
            playlist_url = f"https://www.youtube.com/playlist?list={list_id}"
            return LinkInfo("youtube_mixed", video_url, video_url=video_url, playlist_url=playlist_url)
        return LinkInfo("youtube_video", video_url, video_url=video_url)
    return LinkInfo("unknown", raw)


def _classify_spotify(parts, host: str, raw: str) -> LinkInfo:
    if host in ("spotify.link", "spotify.app.link"):
        return LinkInfo("spotify_link", parts.geturl())
    path = re.sub(r"^/intl-[a-z]{2,3}(?:-[a-z]{2,4})?", "", parts.path or "", flags=re.I)
    segments = [s for s in path.split("/") if s and s != "embed"]
    for kind in ("track", "album", "playlist", "artist"):
        if kind in segments:
            index = segments.index(kind)
            if len(segments) > index + 1:
                item_id = re.sub(r"[^A-Za-z0-9]", "", segments[index + 1])
                if item_id:
                    return LinkInfo(f"spotify_{kind}", f"https://open.spotify.com/{kind}/{item_id}")
    return LinkInfo("unknown", raw)


def resolve_short_link(url: str) -> str:
    resp = requests.head(url, allow_redirects=True, timeout=15, headers=USER_AGENT)
    return resp.url


# --------------------------------------------------------------------------- YouTube

_BRACKET_NOISE = re.compile(
    r"\s*[\(\[\{][^\)\]\}]*\b(?:official|officiel|offizielle?s?|video|audio|lyrics?|lyric\s*video|"
    r"visuali[sz]er|hd|hq|4k|1080p|720p|clip|spot|tekst|prevod|explicit|clean|radio\s*edit|"
    r"mv|m/v|out\s*now|premiere|full\s*version)\b[^\)\]\}]*[\)\]\}]",
    re.I,
)
_PIPE_NOISE = re.compile(
    r"\s*\|\s*[^|]*\b(?:official|video|audio|lyrics?|hd|4k|premiere|spot|visuali[sz]er)\b[^|]*$",
    re.I,
)
_TRAILING_NOISE = re.compile(
    r"\s*(?:[-–—|/•]\s*)?(?:official\s+(?:music\s+|lyric\s+)?video|official\s+audio|"
    r"official\s+hd\s+video|lyric\s+video|lyrics|music\s+video|hd|hq|4k)\s*$",
    re.I,
)
_WS = re.compile(r"\s+")


def clean_title(title: str) -> str:
    """Ukloni uobičajeni šum iz naslova YouTube videa: (Official Video), [Lyrics], HD…"""
    text = title or ""
    for _ in range(3):
        text = _BRACKET_NOISE.sub("", text)
    text = _PIPE_NOISE.sub("", text)
    text = _TRAILING_NOISE.sub("", text)
    text = _WS.sub(" ", text).strip(" -–—|:•")
    return text or (title or "").strip()


def clean_uploader(name: str) -> str:
    text = re.sub(r"\s*-\s*Topic$", "", name or "", flags=re.I)
    text = re.sub(r"VEVO$", "", text, flags=re.I)
    text = re.sub(r"\s+(?:Official|Music|TV|Records|Channel)$", "", text, flags=re.I)
    return text.strip() or (name or "").strip()


def _split_artists(text: str) -> list[str]:
    parts = re.split(r"\s*(?:,|&|\bfeat\.?|\bft\.?)\s*", text, flags=re.I)
    names = [p.strip() for p in parts if p.strip()]
    return names or [text.strip()]


def split_artist_title(title: str, uploader: str) -> tuple[list[str], str]:
    """Iz naslova videa izvuci (izvođači, naslov pjesme). Bez separatora, izvođač je kanal."""
    text = clean_title(title)
    for sep in (" - ", " – ", " — ", " ‒ ", " | ", " // "):
        if sep in text:
            artist, song = text.split(sep, 1)
            artist, song = artist.strip(), song.strip()
            if artist and song:
                return _split_artists(artist), song
    uploader_name = clean_uploader(uploader)
    return ([uploader_name] if uploader_name else []), text


class YdlLogger:
    """Preusmjerava poruke yt-dlp-a u naš log umjesto na konzolu."""

    def debug(self, msg: str) -> None:
        if not msg.startswith("[debug] "):
            log.debug("yt-dlp: %s", msg)

    def info(self, msg: str) -> None:
        log.info("yt-dlp: %s", msg)

    def warning(self, msg: str) -> None:
        log.warning("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        log.error("yt-dlp: %s", msg)


_FRIENDLY = [
    ("Sign in to confirm", "YouTube traži prijavu (provjera bota). U postavkama uključi kolačiće iz browsera."),
    ("Sign in to confirm your age", "Video ima dobno ograničenje. U postavkama uključi kolačiće iz browsera."),
    ("Video unavailable", "Video nije dostupan."),
    ("Private video", "Video je privatan."),
    ("This video has been removed", "Video je uklonjen."),
    ("is not a valid URL", "Link nije ispravan."),
    ("Unable to download webpage", "Ne mogu se povezati (provjeri internet vezu)."),
    ("Requested format is not available", "Traženi audio format nije dostupan."),
    ("No supported JavaScript runtime", "Nedostaje JavaScript runtime (Deno). Preuzmi ga u postavkama."),
    ("HTTP Error 429", "YouTube privremeno ograničava zahtjeve (429). Pokušaj kasnije."),
    ("HTTP Error 403", "YouTube je odbio zahtjev (403). Pokušaj ponovo ili uključi kolačiće."),
]


def friendly_error(exc: BaseException) -> str:
    """Skrati i prevedi poruku greške yt-dlp-a za prikaz korisniku."""
    msg = str(exc) or exc.__class__.__name__
    for needle, text in _FRIENDLY:
        if needle.lower() in msg.lower():
            return text
    msg = re.sub(r"^ERROR:\s*", "", msg)
    msg = re.sub(r"^\[[^\]]+\]\s*[\w-]+:\s*", "", msg)
    msg = msg.split("\n", 1)[0].strip()
    return msg[:220] if msg else "Nepoznata greška."


def _yt_thumbs(video_id: str, entry: dict) -> tuple[str, list[str]]:
    """Vrati (mala slika za listu, kandidati za omot u MP3 – od najbolje prema lošijoj)."""
    small = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg" if video_id else ""
    candidates: list[str] = []
    if entry.get("thumbnail"):
        candidates.append(entry["thumbnail"])
    thumbs = entry.get("thumbnails") or []
    for thumb in sorted(
        thumbs,
        key=lambda t: ((t.get("preference") or 0), (t.get("width") or 0)),
        reverse=True,
    ):
        url = thumb.get("url")
        if url and url not in candidates:
            candidates.append(url)
    if video_id:
        for name in ("maxresdefault", "sddefault", "hqdefault"):
            url = f"https://i.ytimg.com/vi/{video_id}/{name}.jpg"
            if url not in candidates:
                candidates.append(url)
    if not small and candidates:
        small = candidates[-1]
    return small, candidates[:6]


def apply_full_metadata(track: Track, info: dict) -> Track:
    """Popuni ili poboljšaj podatke pjesme iz punog yt-dlp info rječnika."""
    video_id = info.get("id") or ""
    if info.get("track"):
        track.title = str(info["track"])
        artists = info.get("artists") or ([info["artist"]] if info.get("artist") else None)
        artists = artists or info.get("creators") or []
        if artists:
            track.artists = [str(a) for a in artists]
        if info.get("album"):
            track.album = str(info["album"])
    elif not track.title:
        artists, title = split_artist_title(
            info.get("title") or "", info.get("uploader") or info.get("channel") or ""
        )
        track.title = title
        if artists:
            track.artists = artists
    if not track.year:
        year = info.get("release_year") or (info.get("upload_date") or "")[:4]
        if year:
            track.year = str(year)
    if info.get("duration"):
        try:
            track.duration = int(info["duration"])
        except (TypeError, ValueError):
            pass
    small, candidates = _yt_thumbs(video_id, info)
    track.cover_url = track.cover_url or small
    if candidates:
        track.cover_candidates = candidates
    return track


def _track_from_flat(entry: dict, position: int, total: int, collection: str, collection_id: str) -> Track:
    video_id = entry.get("id") or ""
    url = f"https://www.youtube.com/watch?v={video_id}" if video_id else (entry.get("url") or "")
    artists, title = split_artist_title(
        entry.get("title") or "", entry.get("uploader") or entry.get("channel") or ""
    )
    small, candidates = _yt_thumbs(video_id, entry)
    duration = None
    if entry.get("duration"):
        try:
            duration = int(entry["duration"])
        except (TypeError, ValueError):
            duration = None
    return Track(
        source="youtube",
        url=url,
        title=title or "Nepoznata pjesma",
        artists=artists,
        duration=duration,
        cover_url=small,
        cover_candidates=candidates,
        collection=collection,
        collection_kind="playlist",
        collection_id=collection_id,
        position=position,
        total=total,
    )


def analyze_youtube(link: LinkInfo, ydl_extra: dict) -> tuple[list[Track], Optional[dict]]:
    """Vrati (pjesme, podaci o playlisti ili None) za YouTube link."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    is_playlist = link.kind == "youtube_playlist"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": YdlLogger(),
        "socket_timeout": 30,
        "retries": 3,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": not is_playlist,
        "ignoreerrors": is_playlist,
        **ydl_extra,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(link.url, download=False)
    except DownloadError as exc:
        raise SourceError(friendly_error(exc)) from exc
    except Exception as exc:
        log.exception("YouTube analiza nije uspjela: %s", link.url)
        raise SourceError(f"YouTube greška: {friendly_error(exc)}") from exc
    if not info:
        raise SourceError("YouTube nije vratio podatke za ovaj link.")

    if info.get("_type") == "playlist" or "entries" in info:
        entries = [e for e in (info.get("entries") or []) if e]
        entries = [
            e for e in entries if (e.get("title") or "") not in ("[Private video]", "[Deleted video]")
        ]
        if not entries:
            raise SourceError("Playlista je prazna ili nedostupna.")
        name = info.get("title") or "YouTube playlista"
        total = len(entries)
        tracks = [_track_from_flat(e, i + 1, total, name, link.url) for i, e in enumerate(entries)]
        collection = {"name": name, "kind": "playlist", "url": link.url, "count": total, "id": link.url}
        return tracks, collection

    video_id = info.get("id") or ""
    url = info.get("webpage_url") or (f"https://www.youtube.com/watch?v={video_id}" if video_id else link.url)
    track = apply_full_metadata(Track(source="youtube", url=url, title=""), info)
    if not track.title:
        track.title = info.get("title") or "Nepoznata pjesma"
    return [track], None


# --------------------------------------------------------------------------- Spotify

_spotify_lock = threading.Lock()
_spotify_key: Optional[tuple[str, str]] = None


def ensure_spotify_client(client_id: str, client_secret: str) -> None:
    """Inicijaliziraj spotdl Spotify klijent (jednom, ili ponovo kada se ključevi promijene)."""
    global _spotify_key
    key = ((client_id or "").strip(), (client_secret or "").strip())
    with _spotify_lock:
        if _spotify_key == key:
            return
        from spotdl.utils.config import DEFAULT_CONFIG
        from spotdl.utils.spotify import SpotifyClient

        SpotifyClient._instance = None  # dopusti ponovnu inicijalizaciju s novim ključevima
        use_official = bool(key[0] and key[1])
        SpotifyClient.init(
            client_id=key[0] or DEFAULT_CONFIG["client_id"],
            client_secret=key[1] or DEFAULT_CONFIG["client_secret"],
            user_auth=False,
            no_cache=False,
            headless=True,
            use_official_api=use_official,
        )
        _spotify_key = key
        log.info("Spotify klijent spreman (%s API).", "službeni" if use_official else "besplatni")


def _short(exc: BaseException) -> str:
    msg = str(exc).strip().split("\n", 1)[0]
    return msg[:200] if msg else exc.__class__.__name__


def _song_from_track_response(raw: dict):
    """Napravi spotdl Song iz jednog odgovora za pjesmu (bez dodatnih poziva za izvođača i album).

    Svaki Spotify poziv traje nekoliko sekundi, pa za pojedinačnu pjesmu preskačemo dva od tri poziva
    koje spotdl inače radi; sve što treba za tagove već je u odgovoru za pjesmu.
    """
    from spotdl.types.song import Song

    album = raw.get("album") or {}
    artists = [a["name"] for a in raw.get("artists") or [] if a.get("name")]
    if not raw.get("name") or not artists or not raw.get("duration_ms"):
        raise KeyError("nepotpun odgovor")
    album_artists = [a["name"] for a in album.get("artists") or [] if a.get("name")] or artists
    release_date = str(album.get("release_date") or "")
    year = int(release_date[:4]) if release_date[:4].isdigit() else 0
    images = sorted(album.get("images") or [], key=lambda i: i.get("width") or 0, reverse=True)
    cover_url = images[0].get("url") if images else None
    external_urls = raw.get("external_urls") or {}
    return Song(
        name=raw["name"],
        artists=artists,
        artist=artists[0],
        artist_id=(raw.get("artists") or [{}])[0].get("id"),
        album_id=album.get("id"),
        album_name=album.get("name") or "",
        album_artist=album_artists[0],
        album_type=album.get("album_type"),
        copyright_text=None,
        genres=[g for g in (album.get("genres") or []) if g],
        disc_number=int(raw.get("disc_number") or 1),
        disc_count=1,
        duration=int(int(raw["duration_ms"]) / 1000),
        year=year,
        date=release_date,
        track_number=int(raw.get("track_number") or 1),
        tracks_count=int(album.get("total_tracks") or 1),
        song_id=raw.get("id") or raw.get("track_id") or "",
        explicit=bool(raw.get("explicit", False)),
        publisher="",
        url=external_urls.get("spotify") or f"https://open.spotify.com/track/{raw.get('id', '')}",
        isrc=(raw.get("external_ids") or {}).get("isrc") or None,
        cover_url=cover_url,
        popularity=raw.get("popularity"),
    )


def _fetch_songs(link: LinkInfo) -> list:
    from spotdl.utils.search import get_simple_songs
    from spotdl.utils.spotify import SpotifyClient

    if link.kind == "spotify_track":
        try:
            raw = SpotifyClient().track(link.url)
            if raw:
                return [_song_from_track_response(raw)]
        except Exception as exc:
            log.warning("Brzi dohvat pjesme nije uspio (%s), koristim spotdl: %s", link.url, _short(exc))
    return get_simple_songs([link.url])


def analyze_spotify(link: LinkInfo, client_id: str, client_secret: str) -> tuple[list[Track], Optional[dict]]:
    """Vrati (pjesme, podaci o albumu/playlisti ili None) za Spotify link."""
    if link.kind == "spotify_link":
        try:
            resolved = classify(resolve_short_link(link.url))
        except Exception as exc:
            raise SourceError(f"Ne mogu otvoriti skraćeni Spotify link: {_short(exc)}") from exc
        if not resolved.is_spotify or resolved.kind == "spotify_link":
            raise SourceError("Skraćeni Spotify link ne vodi na pjesmu, album ni playlistu.")
        link = resolved

    try:
        ensure_spotify_client(client_id, client_secret)
    except Exception as exc:
        log.exception("Spotify klijent nije inicijaliziran")
        raise SourceError(f"Spotify klijent nije spreman: {_short(exc)}") from exc

    try:
        songs = _fetch_songs(link)
    except Exception as exc:
        log.exception("Spotify analiza nije uspjela: %s", link.url)
        raise SourceError(f"Spotify: {_short(exc)}") from exc
    if not songs:
        raise SourceError("Spotify nije vratio nijednu pjesmu za ovaj link.")

    kind = link.kind.split("_", 1)[1]  # track | album | playlist | artist
    is_list = kind != "track"
    list_name = songs[0].list_name if is_list else None
    if is_list and not list_name:
        list_name = {"album": "Album", "playlist": "Playlista", "artist": "Izvođač"}[kind]

    tracks: list[Track] = []
    for index, song in enumerate(songs, start=1):
        cover = song.cover_url or None
        tracks.append(
            Track(
                source="spotify",
                url=song.url or link.url,
                title=song.name or "Nepoznata pjesma",
                artists=list(song.artists or []),
                album=song.album_name or "",
                album_artist=song.album_artist or "",
                duration=int(song.duration) if song.duration else None,
                cover_url=cover,
                cover_candidates=[cover] if cover else [],
                track_number=song.track_number or None,
                track_total=song.tracks_count or None,
                disc_number=song.disc_number or None,
                year=str(song.year) if song.year else None,
                genres=[g.strip() for g in (song.genres or []) if g and g.strip()][:3],
                collection=list_name if is_list else None,
                collection_kind=kind if is_list else None,
                collection_id=link.url if is_list else None,
                position=(song.list_position or index) if is_list else None,
                total=(song.list_length or len(songs)) if is_list else None,
                spotify_song=song,
            )
        )

    collection = None
    if is_list:
        collection = {"name": list_name, "kind": kind, "url": link.url, "count": len(tracks), "id": link.url}
    return tracks, collection
