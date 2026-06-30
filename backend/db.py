"""Database schema, connection helpers, and queries for the music app."""
from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List, Optional

# Resolve paths relative to this file so the app works from any CWD.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_PATH = os.environ.get("DB_PATH", os.path.join(DATA_DIR, "music.db"))
COVERS_DIR = os.environ.get("COVERS_DIR", os.path.join(DATA_DIR, "covers"))

# WAL improves read/write concurrency locally, but it is unreliable on the
# SMB-mounted Azure Files share used in production (see AGENTS.md), so it is
# opt-out by default there. Set SQLITE_WAL=1 to force it on.
_WAL_ENABLED = os.environ.get("SQLITE_WAL", "0") == "1"
# Wait up to this long (ms) for a competing writer (e.g. a rescan) instead of
# immediately raising "database is locked".
_BUSY_TIMEOUT_MS = int(os.environ.get("SQLITE_BUSY_TIMEOUT_MS", "5000"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS artists (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS albums (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    artist_id  INTEGER REFERENCES artists(id),
    year       INTEGER,
    cover_path TEXT,
    UNIQUE(title, artist_id)
);

CREATE TABLE IF NOT EXISTS tracks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    title     TEXT NOT NULL,
    album_id  INTEGER REFERENCES albums(id),
    artist_id INTEGER REFERENCES artists(id),
    track_no  INTEGER,
    duration  REAL,
    file_path TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_tracks_album  ON tracks(album_id);
CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist_id);
CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums(artist_id);

CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
    kind,        -- 'track' | 'album' | 'artist'
    ref_id UNINDEXED,
    name,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS playlists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    track_id    INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, track_id)
);

CREATE INDEX IF NOT EXISTS idx_playlist_tracks_pos
    ON playlist_tracks(playlist_id, position);
"""


def ensure_dirs() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(COVERS_DIR, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = %d" % _BUSY_TIMEOUT_MS)
    if _WAL_ENABLED:
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: Optional[sqlite3.Connection] = None) -> None:
    own = conn is None
    if conn is None:
        conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    if own:
        conn.close()


# --- Upsert helpers (used by the scanner) ---------------------------------

def upsert_artist(conn: sqlite3.Connection, name: str) -> int:
    name = (name or "Unknown Artist").strip() or "Unknown Artist"
    conn.execute("INSERT OR IGNORE INTO artists(name) VALUES (?)", (name,))
    row = conn.execute("SELECT id FROM artists WHERE name = ?", (name,)).fetchone()
    return int(row["id"])


def upsert_album(
    conn: sqlite3.Connection,
    title: str,
    artist_id: int,
    year: Optional[int],
    cover_path: Optional[str],
) -> int:
    title = (title or "Unknown Album").strip() or "Unknown Album"
    conn.execute(
        "INSERT OR IGNORE INTO albums(title, artist_id, year, cover_path) VALUES (?,?,?,?)",
        (title, artist_id, year, cover_path),
    )
    row = conn.execute(
        "SELECT id, cover_path, year FROM albums WHERE title = ? AND artist_id IS ?",
        (title, artist_id),
    ).fetchone()
    album_id = int(row["id"])
    # Backfill cover/year if we learned them from a later track.
    if cover_path and not row["cover_path"]:
        conn.execute("UPDATE albums SET cover_path = ? WHERE id = ?", (cover_path, album_id))
    if year and not row["year"]:
        conn.execute("UPDATE albums SET year = ? WHERE id = ?", (year, album_id))
    return album_id


def upsert_track(
    conn: sqlite3.Connection,
    title: str,
    album_id: int,
    artist_id: int,
    track_no: Optional[int],
    duration: Optional[float],
    file_path: str,
) -> int:
    conn.execute(
        """
        INSERT INTO tracks(title, album_id, artist_id, track_no, duration, file_path)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(file_path) DO UPDATE SET
            title=excluded.title,
            album_id=excluded.album_id,
            artist_id=excluded.artist_id,
            track_no=excluded.track_no,
            duration=excluded.duration
        """,
        (title, album_id, artist_id, track_no, duration, file_path),
    )
    row = conn.execute("SELECT id FROM tracks WHERE file_path = ?", (file_path,)).fetchone()
    return int(row["id"])


# --- Pruning helpers (used by the scanner) --------------------------------

def all_track_paths(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute("SELECT id, file_path FROM tracks").fetchall()


def delete_tracks(conn: sqlite3.Connection, track_ids: List[int]) -> int:
    """Delete tracks by id; cascades to playlist_tracks. Returns rows removed."""
    if not track_ids:
        return 0
    ph = ",".join("?" * len(track_ids))
    cur = conn.execute("DELETE FROM tracks WHERE id IN (%s)" % ph, track_ids)
    return cur.rowcount


def prune_orphans(conn: sqlite3.Connection) -> List[str]:
    """Delete albums with no tracks and artists referenced by nothing.

    Returns the cover_paths of removed albums so the caller can unlink the
    cached image files from disk.
    """
    orphan_albums = conn.execute(
        """
        SELECT id, cover_path FROM albums
        WHERE id NOT IN (
            SELECT DISTINCT album_id FROM tracks WHERE album_id IS NOT NULL
        )
        """
    ).fetchall()
    cover_paths = [r["cover_path"] for r in orphan_albums if r["cover_path"]]
    conn.execute(
        """
        DELETE FROM albums
        WHERE id NOT IN (
            SELECT DISTINCT album_id FROM tracks WHERE album_id IS NOT NULL
        )
        """
    )
    conn.execute(
        """
        DELETE FROM artists
        WHERE id NOT IN (
            SELECT DISTINCT artist_id FROM tracks WHERE artist_id IS NOT NULL
        )
        AND id NOT IN (
            SELECT DISTINCT artist_id FROM albums WHERE artist_id IS NOT NULL
        )
        """
    )
    return cover_paths


def rebuild_search_index(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM search_fts")
    conn.execute(
        "INSERT INTO search_fts(kind, ref_id, name) SELECT 'artist', id, name FROM artists"
    )
    conn.execute(
        "INSERT INTO search_fts(kind, ref_id, name) SELECT 'album', id, title FROM albums"
    )
    conn.execute(
        "INSERT INTO search_fts(kind, ref_id, name) SELECT 'track', id, title FROM tracks"
    )
    conn.commit()


# --- Read queries (used by the API) ---------------------------------------

def _track_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "album_id": row["album_id"],
        "album": row["album"],
        "artist_id": row["artist_id"],
        "artist": row["artist"],
        "track_no": row["track_no"],
        "duration": row["duration"],
    }


TRACK_SELECT = """
SELECT t.id, t.title, t.album_id, t.artist_id, t.track_no, t.duration,
       al.title AS album, ar.name AS artist
FROM tracks t
LEFT JOIN albums al ON t.album_id = al.id
LEFT JOIN artists ar ON t.artist_id = ar.id
"""


def list_tracks(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        TRACK_SELECT + " ORDER BY ar.name, al.title, t.track_no, t.title"
    ).fetchall()
    return [_track_to_dict(r) for r in rows]


def list_albums(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT al.id, al.title, al.year, al.cover_path, al.artist_id,
               ar.name AS artist, COUNT(t.id) AS track_count
        FROM albums al
        LEFT JOIN artists ar ON al.artist_id = ar.id
        LEFT JOIN tracks t ON t.album_id = al.id
        GROUP BY al.id
        ORDER BY ar.name, al.year, al.title
        """
    ).fetchall()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "year": r["year"],
            "artist_id": r["artist_id"],
            "artist": r["artist"],
            "track_count": r["track_count"],
            "has_cover": bool(r["cover_path"]),
        }
        for r in rows
    ]


def get_album(conn: sqlite3.Connection, album_id: int) -> Optional[Dict[str, Any]]:
    al = conn.execute(
        """
        SELECT al.id, al.title, al.year, al.cover_path, al.artist_id, ar.name AS artist
        FROM albums al LEFT JOIN artists ar ON al.artist_id = ar.id
        WHERE al.id = ?
        """,
        (album_id,),
    ).fetchone()
    if not al:
        return None
    tracks = conn.execute(
        TRACK_SELECT + " WHERE t.album_id = ? ORDER BY t.track_no, t.title",
        (album_id,),
    ).fetchall()
    return {
        "id": al["id"],
        "title": al["title"],
        "year": al["year"],
        "artist_id": al["artist_id"],
        "artist": al["artist"],
        "has_cover": bool(al["cover_path"]),
        "tracks": [_track_to_dict(t) for t in tracks],
    }


def get_track(conn: sqlite3.Connection, track_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        TRACK_SELECT + " WHERE t.id = ?", (track_id,)
    ).fetchone()
    return _track_to_dict(row) if row else None


def get_track_path(conn: sqlite3.Connection, track_id: int) -> Optional[str]:
    row = conn.execute("SELECT file_path FROM tracks WHERE id = ?", (track_id,)).fetchone()
    return row["file_path"] if row else None


def get_album_cover_path(conn: sqlite3.Connection, album_id: int) -> Optional[str]:
    row = conn.execute("SELECT cover_path FROM albums WHERE id = ?", (album_id,)).fetchone()
    return row["cover_path"] if row and row["cover_path"] else None


def _escape_fts(q: str) -> str:
    # Wrap each token in quotes and add a prefix wildcard for type-ahead search.
    tokens = [t for t in q.replace('"', " ").split() if t]
    if not tokens:
        return ""
    return " ".join('"%s"*' % t for t in tokens)


def search(conn: sqlite3.Connection, q: str) -> Dict[str, List[Dict[str, Any]]]:
    match = _escape_fts(q)
    result: Dict[str, List[Dict[str, Any]]] = {"artists": [], "albums": [], "tracks": []}
    if not match:
        return result
    rows = conn.execute(
        "SELECT kind, ref_id FROM search_fts WHERE search_fts MATCH ? LIMIT 100",
        (match,),
    ).fetchall()
    track_ids = [r["ref_id"] for r in rows if r["kind"] == "track"]
    album_ids = [r["ref_id"] for r in rows if r["kind"] == "album"]
    artist_ids = [r["ref_id"] for r in rows if r["kind"] == "artist"]

    if track_ids:
        ph = ",".join("?" * len(track_ids))
        trows = conn.execute(
            TRACK_SELECT + " WHERE t.id IN (%s)" % ph, track_ids
        ).fetchall()
        result["tracks"] = [_track_to_dict(t) for t in trows]
    if album_ids:
        ph = ",".join("?" * len(album_ids))
        arows = conn.execute(
            """
            SELECT al.id, al.title, al.year, al.cover_path, al.artist_id, ar.name AS artist
            FROM albums al LEFT JOIN artists ar ON al.artist_id = ar.id
            WHERE al.id IN (%s)
            """
            % ph,
            album_ids,
        ).fetchall()
        result["albums"] = [
            {
                "id": r["id"],
                "title": r["title"],
                "year": r["year"],
                "artist_id": r["artist_id"],
                "artist": r["artist"],
                "has_cover": bool(r["cover_path"]),
            }
            for r in arows
        ]
    if artist_ids:
        ph = ",".join("?" * len(artist_ids))
        arows = conn.execute(
            "SELECT id, name FROM artists WHERE id IN (%s)" % ph, artist_ids
        ).fetchall()
        result["artists"] = [{"id": r["id"], "name": r["name"]} for r in arows]
    return result


def stats(conn: sqlite3.Connection) -> Dict[str, int]:
    return {
        "artists": conn.execute("SELECT COUNT(*) c FROM artists").fetchone()["c"],
        "albums": conn.execute("SELECT COUNT(*) c FROM albums").fetchone()["c"],
        "tracks": conn.execute("SELECT COUNT(*) c FROM tracks").fetchone()["c"],
    }


# --- Playlists ------------------------------------------------------------

def _touch_playlist(conn: sqlite3.Connection, playlist_id: int) -> None:
    conn.execute(
        "UPDATE playlists SET updated_at = datetime('now') WHERE id = ?",
        (playlist_id,),
    )


def list_playlists(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.id, p.name, p.created_at, p.updated_at,
               COUNT(pt.track_id) AS track_count
        FROM playlists p
        LEFT JOIN playlist_tracks pt ON pt.playlist_id = p.id
        GROUP BY p.id
        ORDER BY p.name COLLATE NOCASE
        """
    ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "track_count": r["track_count"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def get_playlist(conn: sqlite3.Connection, playlist_id: int) -> Optional[Dict[str, Any]]:
    p = conn.execute(
        "SELECT id, name, created_at, updated_at FROM playlists WHERE id = ?",
        (playlist_id,),
    ).fetchone()
    if not p:
        return None
    tracks = conn.execute(
        TRACK_SELECT
        + """
        JOIN playlist_tracks pt ON pt.track_id = t.id
        WHERE pt.playlist_id = ?
        ORDER BY pt.position
        """,
        (playlist_id,),
    ).fetchall()
    return {
        "id": p["id"],
        "name": p["name"],
        "created_at": p["created_at"],
        "updated_at": p["updated_at"],
        "tracks": [_track_to_dict(t) for t in tracks],
    }


def create_playlist(conn: sqlite3.Connection, name: str) -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("Playlist name is required")
    cur = conn.execute("INSERT INTO playlists(name) VALUES (?)", (name,))
    conn.commit()
    return int(cur.lastrowid)


def rename_playlist(conn: sqlite3.Connection, playlist_id: int, name: str) -> bool:
    name = (name or "").strip()
    if not name:
        raise ValueError("Playlist name is required")
    cur = conn.execute(
        "UPDATE playlists SET name = ?, updated_at = datetime('now') WHERE id = ?",
        (name, playlist_id),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_playlist(conn: sqlite3.Connection, playlist_id: int) -> bool:
    cur = conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
    conn.commit()
    return cur.rowcount > 0


def add_track_to_playlist(
    conn: sqlite3.Connection, playlist_id: int, track_id: int
) -> None:
    next_pos = conn.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 AS pos FROM playlist_tracks WHERE playlist_id = ?",
        (playlist_id,),
    ).fetchone()["pos"]
    conn.execute(
        """
        INSERT INTO playlist_tracks(playlist_id, track_id, position)
        VALUES (?, ?, ?)
        ON CONFLICT(playlist_id, track_id) DO NOTHING
        """,
        (playlist_id, track_id, next_pos),
    )
    _touch_playlist(conn, playlist_id)
    conn.commit()


def remove_track_from_playlist(
    conn: sqlite3.Connection, playlist_id: int, track_id: int
) -> None:
    conn.execute(
        "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
        (playlist_id, track_id),
    )
    # Compact positions so they stay contiguous.
    rows = conn.execute(
        "SELECT track_id FROM playlist_tracks WHERE playlist_id = ? ORDER BY position",
        (playlist_id,),
    ).fetchall()
    for pos, r in enumerate(rows):
        conn.execute(
            "UPDATE playlist_tracks SET position = ? WHERE playlist_id = ? AND track_id = ?",
            (pos, playlist_id, r["track_id"]),
        )
    _touch_playlist(conn, playlist_id)
    conn.commit()


def reorder_playlist(
    conn: sqlite3.Connection, playlist_id: int, track_ids: List[int]
) -> None:
    existing = {
        r["track_id"]
        for r in conn.execute(
            "SELECT track_id FROM playlist_tracks WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchall()
    }
    # Only reorder tracks that actually belong to the playlist; append any
    # that the client omitted so nothing is silently dropped.
    ordered = [tid for tid in track_ids if tid in existing]
    ordered += [tid for tid in existing if tid not in ordered]
    for pos, tid in enumerate(ordered):
        conn.execute(
            "UPDATE playlist_tracks SET position = ? WHERE playlist_id = ? AND track_id = ?",
            (pos, playlist_id, tid),
        )
    _touch_playlist(conn, playlist_id)
    conn.commit()


def playlist_exists(conn: sqlite3.Connection, playlist_id: int) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM playlists WHERE id = ?", (playlist_id,)
        ).fetchone()
        is not None
    )


def track_exists(conn: sqlite3.Connection, track_id: int) -> bool:
    return (
        conn.execute("SELECT 1 FROM tracks WHERE id = ?", (track_id,)).fetchone()
        is not None
    )
