"""Scan a music folder, read ID3 tags, extract cover art, and populate SQLite.

Usage:
    python scanner.py /path/to/music
    MUSIC_DIR=/path/to/music python scanner.py
"""
from __future__ import annotations

import hashlib
import os
import sys
from typing import Optional, Tuple

from mutagen import File as MutagenFile
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3
from mutagen.mp4 import MP4, MP4Cover

import db

AUDIO_EXTS = {".mp3", ".m4a", ".mp4", ".flac", ".ogg", ".opus", ".wav"}


def _first(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else None
    return str(value)


def _parse_track_no(raw) -> Optional[int]:
    s = _first(raw)
    if not s:
        return None
    # Handle "3/12" style track numbers.
    s = s.split("/")[0].strip()
    try:
        return int(s)
    except ValueError:
        return None


def _parse_year(raw) -> Optional[int]:
    s = _first(raw)
    if not s:
        return None
    for i in range(len(s) - 3):
        chunk = s[i : i + 4]
        if chunk.isdigit():
            return int(chunk)
    return None


def _extract_cover_bytes(path: str, audio) -> Optional[Tuple[bytes, str]]:
    """Return (image_bytes, ext) for embedded cover art, if any."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".mp3":
            tags = ID3(path)
            for key in tags.keys():
                if key.startswith("APIC"):
                    apic = tags[key]
                    return apic.data, _mime_ext(apic.mime)
        elif ext == ".flac":
            flac = FLAC(path)
            for pic in flac.pictures:
                if isinstance(pic, Picture) and pic.data:
                    return pic.data, _mime_ext(pic.mime)
        elif ext in (".m4a", ".mp4"):
            mp4 = MP4(path)
            covers = mp4.tags.get("covr") if mp4.tags else None
            if covers:
                cov = covers[0]
                fmt = getattr(cov, "imageformat", None)
                ext2 = ".png" if fmt == MP4Cover.FORMAT_PNG else ".jpg"
                return bytes(cov), ext2
    except Exception:
        return None
    return None


def _mime_ext(mime: Optional[str]) -> str:
    if mime and "png" in mime.lower():
        return ".png"
    return ".jpg"


def _save_cover(album_id: int, data: bytes, ext: str) -> str:
    db.ensure_dirs()
    filename = "%d%s" % (album_id, ext)
    out_path = os.path.join(db.COVERS_DIR, filename)
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path


def scan(music_dir: str) -> dict:
    music_dir = os.path.abspath(os.path.expanduser(music_dir))
    if not os.path.isdir(music_dir):
        raise SystemExit("Music directory not found: %s" % music_dir)

    conn = db.get_connection()
    db.init_db(conn)

    scanned = 0
    skipped = 0
    seen_paths: set[str] = set()

    for root, _dirs, files in os.walk(music_dir):
        for name in sorted(files):
            ext = os.path.splitext(name)[1].lower()
            if ext not in AUDIO_EXTS:
                continue
            path = os.path.join(root, name)
            try:
                audio = MutagenFile(path, easy=True)
            except Exception:
                audio = None
            if audio is None:
                skipped += 1
                continue

            tags = audio.tags or {}
            title = _first(tags.get("title")) or os.path.splitext(name)[0]
            artist = _first(tags.get("artist")) or _first(tags.get("albumartist")) or "Unknown Artist"
            album_artist = _first(tags.get("albumartist")) or artist
            album = _first(tags.get("album")) or "Unknown Album"
            track_no = _parse_track_no(tags.get("tracknumber"))
            year = _parse_year(tags.get("date") or tags.get("year"))
            duration = None
            if getattr(audio, "info", None) is not None:
                duration = getattr(audio.info, "length", None)

            album_artist_id = db.upsert_artist(conn, album_artist)
            track_artist_id = db.upsert_artist(conn, artist)
            album_id = db.upsert_album(conn, album, album_artist_id, year, None)

            # Cover art: only extract once per album (when not already cached).
            if not db.get_album_cover_path(conn, album_id):
                cover = _extract_cover_bytes(path, audio)
                if cover:
                    cover_path = _save_cover(album_id, cover[0], cover[1])
                    conn.execute(
                        "UPDATE albums SET cover_path = ? WHERE id = ?",
                        (cover_path, album_id),
                    )

            db.upsert_track(
                conn, title, album_id, track_artist_id, track_no, duration, path
            )
            seen_paths.add(path)
            scanned += 1

    removed = _prune_missing(conn, seen_paths)

    db.rebuild_search_index(conn)
    conn.commit()
    counts = db.stats(conn)
    conn.close()

    print("Scanned %d tracks (%d skipped, %d removed)." % (scanned, skipped, removed))
    print("Library: %(artists)d artists, %(albums)d albums, %(tracks)d tracks." % counts)
    counts["removed"] = removed
    return counts


def _prune_missing(conn, seen_paths: set) -> int:
    """Remove tracks no longer present on disk, plus newly-orphaned albums,
    artists, and their cached cover files. Returns the track removal count."""
    stale_ids = [
        row["id"] for row in db.all_track_paths(conn) if row["file_path"] not in seen_paths
    ]
    removed = db.delete_tracks(conn, stale_ids)
    if removed:
        for cover_path in db.prune_orphans(conn):
            try:
                os.remove(cover_path)
            except OSError:
                pass
    return removed


def main() -> None:
    music_dir = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MUSIC_DIR")
    if not music_dir:
        print("Usage: python scanner.py /path/to/music", file=sys.stderr)
        raise SystemExit(2)
    scan(music_dir)


if __name__ == "__main__":
    main()
