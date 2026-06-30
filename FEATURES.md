# FEATURES.md

A running log of features and notable changes to the app. **Keep this file
up to date** — see the maintenance note at the bottom.

Newest entries go at the top. Use the date the change was made.

## 2026-06-24 — Reliability fixes (covers, rescan, tests)

Code-review remediation pass — mostly backend hardening plus a user-visible
cover-art fix.

- **AAC/ALAC cover art now works:** fixed a bug where embedded artwork in
  `.m4a`/`.mp4` files was silently dropped during scanning (a bad `MP4Cover`
  reference swallowed by a broad `except`).
- **Rescan no longer blocks the app:** `POST /api/rescan` now runs in the
  background and returns `202` immediately (rejecting overlapping scans with
  `409`); the UI polls the new `GET /api/rescan/status` to completion. Prevents
  a large library scan from freezing the single-worker server.
- **Rescan prunes deleted files:** tracks removed from disk (and their now-empty
  albums, artists, and cached covers) are cleaned up on rescan instead of
  lingering as dead entries.
- **SQLite robustness:** added `busy_timeout` (and opt-in WAL for local use) so
  concurrent reads during a scan don't immediately error with "database is
  locked".
- **CORS tightened:** the wildcard origin is now limited to the Vite dev origin
  and only enabled in dev.
- **Backend test suite:** added `pytest` tests (`backend/tests/`) for Range
  parsing, playlist reorder/compaction, FTS search, and tag parsing; see
  `requirements-dev.txt`.
- **Internal:** migrated the deprecated `@app.on_event("startup")` to a FastAPI
  `lifespan` handler.

---

## 2026-06-24 — Playlists

Added user-created playlists, stored server-side in SQLite.

- **New tables:** `playlists` and `playlist_tracks` (FK to `tracks` with
  `ON DELETE CASCADE`, ordered by `position`). Playlists reference track IDs, so
  they survive rescans.
- **REST API:** `GET/POST /api/playlists`, `GET/PATCH/DELETE /api/playlists/{id}`,
  `POST/DELETE /api/playlists/{id}/tracks`, and `PUT /api/playlists/{id}/tracks`
  (reorder).
- **Playlists nav + views:** a **Playlists** button in the topbar opens a list
  view (create / delete) and a playlist detail view (play, inline rename, remove
  tracks, reorder with up/down buttons).
- **Add to playlist:** every track row now has a **"⋯" menu** to add the track to
  an existing playlist or create a new one on the spot (works from album and
  search track lists).

---

## 2026-06-24 — Safari / iPhone mobile UX

Optimized the UI for mobile Safari (tested on iPhone 15).

- **Safe layout on iOS:** switched the app shell to `100dvh` and added
  `env(safe-area-inset-*)` padding (plus `viewport-fit=cover`) so the player
  bar is no longer hidden behind Safari's chrome or the home indicator.
- **No more zoom-on-focus:** bumped the search input to 16px so iOS stops
  auto-zooming when it's tapped.
- **Mobile player layout:** restacked the player on narrow screens — track
  info and transport controls on top, a full-width seek bar below — with 44px
  touch targets.
- **Monochrome icons:** replaced the emoji transport controls (⏮ ▶ ⏸ ⏭ 🔊)
  with clean SVG icons that inherit the UI color (`src/components/Icons.tsx`).
- **Lock screen / Control Center:** added Media Session API integration so
  track metadata, album artwork, play/pause/skip, and the scrubber position
  show up on the iOS lock screen and Control Center.

---

## Maintenance note (for AI agents and humans)

**Whenever you add or meaningfully change a user-facing feature, add an entry
to the top of this file in the same commit as the change.** Each entry should
have a date heading, a short summary, and a bulleted list of what changed and
why. Don't let this file fall behind the code.
