"""FastAPI application: library browsing, search, and range-based streaming."""
from __future__ import annotations

import mimetypes
import os
import re
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import scanner

# Where the built UI lives (overridable for containers/cloud layouts). Computed
# up front because it also decides whether we're running in "dev" mode below.
_FRONTEND_DIST = os.environ.get("FRONTEND_DIST") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist"
)
_SERVE_FRONTEND = os.path.isdir(_FRONTEND_DIST)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="My Music App", lifespan=lifespan)

# CORS is only needed in dev, where the Vite dev server runs on a separate
# origin (:5173) and talks to this API directly. In prod the built UI is served
# same-origin, so we don't open it up. Force-enable with DEV_CORS=1.
if os.environ.get("DEV_CORS", "0") == "1" or not _SERVE_FRONTEND:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _conn():
    return db.get_connection()


# Rescan runs in the background; this lock/state lets us reject overlapping
# scans and report progress to the UI. The lock is acquired in the request
# handler and released by the worker thread when the scan finishes.
_scan_lock = threading.Lock()
_scan_state: dict = {"status": "idle", "last_counts": None, "error": None}


def _run_scan(music_dir: str) -> None:
    try:
        _scan_state["last_counts"] = scanner.scan(music_dir)
        _scan_state["error"] = None
    except Exception as exc:  # noqa: BLE001 - surface any scan failure to the UI
        _scan_state["error"] = str(exc)
    finally:
        _scan_state["status"] = "idle"
        _scan_lock.release()


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


@app.post("/api/rescan", status_code=202)
def rescan(background_tasks: BackgroundTasks):
    music_dir = os.environ.get("MUSIC_DIR")
    if not music_dir:
        raise HTTPException(status_code=400, detail="MUSIC_DIR is not configured")
    # Non-blocking: a large scan must not tie up the (single) worker. Guard
    # against overlapping scans so we never have two writers on the SQLite DB.
    if not _scan_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A scan is already running")
    _scan_state.update(status="running", error=None)
    background_tasks.add_task(_run_scan, music_dir)
    return {"status": "running"}


@app.get("/api/rescan/status")
def rescan_status():
    return _scan_state


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
# If frontend/dist exists (computed at import time as _FRONTEND_DIST), serve it
# as static files at the root so the whole app runs from one process.
if _SERVE_FRONTEND:
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
