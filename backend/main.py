"""FastAPI application: library browsing, search, and range-based streaming."""
from __future__ import annotations

import mimetypes
import os
import re
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import scanner

app = FastAPI(title="My Music App")

# In dev the Vite server runs on a different origin; allow it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


def _conn():
    return db.get_connection()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/stats")
def get_stats():
    conn = _conn()
    try:
        return db.stats(conn)
    finally:
        conn.close()


@app.get("/api/tracks")
def get_tracks():
    conn = _conn()
    try:
        return db.list_tracks(conn)
    finally:
        conn.close()


@app.get("/api/albums")
def get_albums():
    conn = _conn()
    try:
        return db.list_albums(conn)
    finally:
        conn.close()


@app.get("/api/albums/{album_id}")
def get_album(album_id: int):
    conn = _conn()
    try:
        album = db.get_album(conn, album_id)
        if not album:
            raise HTTPException(status_code=404, detail="Album not found")
        return album
    finally:
        conn.close()


@app.get("/api/search")
def search(q: str = Query("", min_length=0)):
    conn = _conn()
    try:
        return db.search(conn, q)
    finally:
        conn.close()


# --- Playlists ------------------------------------------------------------

class PlaylistCreate(BaseModel):
    name: str


class PlaylistRename(BaseModel):
    name: str


class PlaylistTrackAdd(BaseModel):
    track_id: int


class PlaylistReorder(BaseModel):
    track_ids: list[int]


@app.get("/api/playlists")
def get_playlists():
    conn = _conn()
    try:
        return db.list_playlists(conn)
    finally:
        conn.close()


@app.post("/api/playlists", status_code=201)
def create_playlist(body: PlaylistCreate):
    conn = _conn()
    try:
        try:
            pid = db.create_playlist(conn, body.name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return db.get_playlist(conn, pid)
    finally:
        conn.close()


@app.get("/api/playlists/{playlist_id}")
def get_playlist(playlist_id: int):
    conn = _conn()
    try:
        playlist = db.get_playlist(conn, playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        return playlist
    finally:
        conn.close()


@app.patch("/api/playlists/{playlist_id}")
def rename_playlist(playlist_id: int, body: PlaylistRename):
    conn = _conn()
    try:
        try:
            ok = db.rename_playlist(conn, playlist_id, body.name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not ok:
            raise HTTPException(status_code=404, detail="Playlist not found")
        return db.get_playlist(conn, playlist_id)
    finally:
        conn.close()


@app.delete("/api/playlists/{playlist_id}", status_code=204)
def delete_playlist(playlist_id: int):
    conn = _conn()
    try:
        if not db.delete_playlist(conn, playlist_id):
            raise HTTPException(status_code=404, detail="Playlist not found")
        return Response(status_code=204)
    finally:
        conn.close()


@app.post("/api/playlists/{playlist_id}/tracks")
def add_playlist_track(playlist_id: int, body: PlaylistTrackAdd):
    conn = _conn()
    try:
        if not db.playlist_exists(conn, playlist_id):
            raise HTTPException(status_code=404, detail="Playlist not found")
        if not db.track_exists(conn, body.track_id):
            raise HTTPException(status_code=404, detail="Track not found")
        db.add_track_to_playlist(conn, playlist_id, body.track_id)
        return db.get_playlist(conn, playlist_id)
    finally:
        conn.close()


@app.delete("/api/playlists/{playlist_id}/tracks/{track_id}")
def remove_playlist_track(playlist_id: int, track_id: int):
    conn = _conn()
    try:
        if not db.playlist_exists(conn, playlist_id):
            raise HTTPException(status_code=404, detail="Playlist not found")
        db.remove_track_from_playlist(conn, playlist_id, track_id)
        return db.get_playlist(conn, playlist_id)
    finally:
        conn.close()


@app.put("/api/playlists/{playlist_id}/tracks")
def reorder_playlist_tracks(playlist_id: int, body: PlaylistReorder):
    conn = _conn()
    try:
        if not db.playlist_exists(conn, playlist_id):
            raise HTTPException(status_code=404, detail="Playlist not found")
        db.reorder_playlist(conn, playlist_id, body.track_ids)
        return db.get_playlist(conn, playlist_id)
    finally:
        conn.close()


@app.post("/api/rescan")
def rescan():
    music_dir = os.environ.get("MUSIC_DIR")
    if not music_dir:
        raise HTTPException(status_code=400, detail="MUSIC_DIR is not configured")
    counts = scanner.scan(music_dir)
    return counts


@app.get("/api/covers/{album_id}")
def get_cover(album_id: int):
    conn = _conn()
    try:
        path = db.get_album_cover_path(conn, album_id)
    finally:
        conn.close()
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Cover not found")
    return FileResponse(path)


_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
CHUNK_SIZE = 1024 * 1024  # 1 MiB


@app.head("/api/stream/{track_id}")
@app.get("/api/stream/{track_id}")
def stream(track_id: int, request: Request):
    conn = _conn()
    try:
        path = db.get_track_path(conn, track_id)
    finally:
        conn.close()
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Track file not found")

    file_size = os.path.getsize(path)
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    range_header = request.headers.get("range") or request.headers.get("Range")

    if range_header is None:
        # No range: stream whole file but still advertise range support.
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        }
        if request.method == "HEAD":
            headers["Content-Type"] = content_type
            return Response(status_code=200, headers=headers)
        return StreamingResponse(
            _iter_file(path, 0, file_size - 1),
            status_code=200,
            media_type=content_type,
            headers=headers,
        )

    match = _RANGE_RE.match(range_header.strip())
    if not match:
        raise HTTPException(status_code=400, detail="Invalid Range header")

    start_s, end_s = match.group(1), match.group(2)
    if start_s == "" and end_s == "":
        raise HTTPException(status_code=400, detail="Invalid Range header")

    if start_s == "":
        # Suffix range: last N bytes.
        length = int(end_s)
        start = max(file_size - length, 0)
        end = file_size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s != "" else file_size - 1

    end = min(end, file_size - 1)
    if start > end or start >= file_size:
        return Response(
            status_code=416,
            headers={
                "Content-Range": "bytes */%d" % file_size,
                "Accept-Ranges": "bytes",
            },
        )

    length = end - start + 1
    headers = {
        "Content-Range": "bytes %d-%d/%d" % (start, end, file_size),
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
    }
    if request.method == "HEAD":
        headers["Content-Type"] = content_type
        return Response(status_code=206, headers=headers)
    return StreamingResponse(
        _iter_file(path, start, end),
        status_code=206,
        media_type=content_type,
        headers=headers,
    )


def _iter_file(path: str, start: int, end: int):
    """Yield file bytes from start..end inclusive in chunks."""
    remaining = end - start + 1
    with open(path, "rb") as f:
        f.seek(start)
        while remaining > 0:
            chunk = f.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


# --- Serve built frontend in "prod" mode ----------------------------------
# If frontend/dist exists, serve it as static files at the root. The location
# can be overridden with FRONTEND_DIST (useful in containers/cloud layouts).
_FRONTEND_DIST = os.environ.get("FRONTEND_DIST") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist"
)
if os.path.isdir(_FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
