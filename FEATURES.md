# FEATURES.md

A running log of features and notable changes to the app. **Keep this file
up to date** — see the maintenance note at the bottom.

Newest entries go at the top. Use the date the change was made.

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
