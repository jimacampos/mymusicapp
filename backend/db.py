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
"""


def ensure_dirs() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(COVERS_DIR, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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
