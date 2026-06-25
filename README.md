# mymusicapp

A self-hosted "Spotify for me" — stream your local music library from a web UI.

**Stack:** FastAPI + SQLite backend · React (Vite + TypeScript) frontend.

## Features (MVP)

- Scans a music folder and reads ID3 tags (title, artist, album, track #, year, cover art) via `mutagen`
- Stores metadata in SQLite with an FTS5 full-text search index
- Browse albums in a grid, open album detail, search tracks/albums/artists
- Create **playlists**: add tracks via a "⋯" menu, reorder, rename, and play them
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
| `FRONTEND_DIST` | `../frontend/dist` | Built UI to serve (override for containers) |
| `PORT`       | `8000`               | Port uvicorn binds (set by the Docker image) |

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
| GET    | `/api/playlists`      | List playlists                       |
| POST   | `/api/playlists`      | Create a playlist `{name}`           |
| GET    | `/api/playlists/{id}` | Playlist detail + ordered tracks     |
| PATCH  | `/api/playlists/{id}` | Rename a playlist `{name}`           |
| DELETE | `/api/playlists/{id}` | Delete a playlist                    |
| POST   | `/api/playlists/{id}/tracks` | Add a track `{track_id}`      |
| DELETE | `/api/playlists/{id}/tracks/{track_id}` | Remove a track     |
| PUT    | `/api/playlists/{id}/tracks` | Reorder `{track_ids: [...]}`  |

## Docker

The repo ships a multi-stage `Dockerfile` that builds the frontend and serves
it together with the API from one container:

```bash
docker build -t mymusicapp .
docker run -p 8000:8000 \
  -v /path/to/music:/music -e MUSIC_DIR=/music \
  -v /path/to/data:/data   -e DATA_DIR=/data \
  mymusicapp
# open http://localhost:8000  (then click Rescan)
```

## Deploy to Azure

Run the app on **Azure App Service for Containers** with the library + database
on **mounted Azure Files shares**, gated by **Easy Auth** (Microsoft Entra ID),
shipped by the `Deploy to Azure` GitHub Actions workflow.

See **[`deploy/README.md`](deploy/README.md)** for the full walkthrough. In short:

1. `./deploy/azure-setup.sh` — provision RG, ACR, storage + shares, plan, Web App
2. `./deploy/github-oidc-setup.sh` — create the GitHub OIDC identity, then add the
   printed secrets/variables under *repo → Settings → Secrets and variables → Actions*
3. Push to `main` to build + deploy the image
4. Upload music to the `music` share, then click **Rescan**
5. `./deploy/easy-auth-setup.sh` — require Entra ID sign-in

> Run a single instance only — SQLite lives on the SMB-mounted `data` share and
> concurrent writers can corrupt it.
