# mymusicapp

A self-hosted "Spotify for me" — stream your local music library from a web UI.

**Stack:** FastAPI + SQLite backend · React (Vite + TypeScript) frontend.

## Features (MVP)

- Scans a music folder and reads ID3 tags (title, artist, album, track #, year, cover art) via `mutagen`
- Stores metadata in SQLite with an FTS5 full-text search index
- Browse albums in a grid, open album detail, search tracks/albums/artists
- Streams audio with **HTTP Range requests** (`206 Partial Content`) so seeking works
- Persistent player bar: play/pause, seek, next/previous, volume
- Keyboard shortcuts: `Space` play/pause, `←/→` seek 5s, `Shift+←/→` prev/next
- Remembers last volume; one-click **Rescan**

## Project layout

```
backend/
  main.py          FastAPI app + routes (incl. range streaming)
  scanner.py       library scan / tag reading / cover extraction
  db.py            SQLite schema + queries
  requirements.txt
frontend/          Vite + React + TypeScript
  src/
    api.ts
    player.tsx     audio playback context
    components/Player.tsx, TrackList.tsx
    views/Library.tsx, Album.tsx, Search.tsx
```

## Setup

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Scan your library

```bash
# from backend/ with the venv active
python scanner.py /path/to/your/music
# or:  MUSIC_DIR=/path/to/your/music python scanner.py
```

This populates `backend/data/music.db` and caches cover art under `backend/data/covers/`.

### 3. Run the API

```bash
# MUSIC_DIR enables the in-app "Rescan" button
MUSIC_DIR=/path/to/your/music uvicorn main:app --reload --port 8000
```

## Frontend

### Dev mode (hot reload, proxies `/api` → :8000)

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

### Prod mode (FastAPI serves the built UI)

```bash
cd frontend
npm run build        # outputs frontend/dist
```

When `frontend/dist` exists, the FastAPI server serves it at `http://localhost:8000/`,
so the whole app runs from a single process.

## Configuration

Environment variables (all optional):

| Var          | Default              | Purpose                                  |
|--------------|----------------------|------------------------------------------|
| `MUSIC_DIR`  | —                    | Library path; required for `/api/rescan` |
| `DATA_DIR`   | `backend/data`       | Where the DB + covers live               |
| `DB_PATH`    | `$DATA_DIR/music.db` | SQLite database file                     |
| `COVERS_DIR` | `$DATA_DIR/covers`   | Cached cover art                         |

## API

| Method | Path                  | Description                          |
|--------|-----------------------|--------------------------------------|
| GET    | `/api/albums`         | List albums                          |
| GET    | `/api/albums/{id}`    | Album detail + tracks                |
| GET    | `/api/tracks`         | All tracks                           |
| GET    | `/api/search?q=`      | FTS search (artists/albums/tracks)   |
| GET    | `/api/stream/{id}`    | Stream audio (supports Range)        |
| GET    | `/api/covers/{id}`    | Album cover image                    |
| POST   | `/api/rescan`         | Re-scan `MUSIC_DIR`                  |
| GET    | `/api/stats`          | Library counts                       |
