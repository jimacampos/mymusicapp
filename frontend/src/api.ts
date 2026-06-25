export interface Track {
  id: number;
  title: string;
  album_id: number | null;
  album: string | null;
  artist_id: number | null;
  artist: string | null;
  track_no: number | null;
  duration: number | null;
}

export interface AlbumSummary {
  id: number;
  title: string;
  year: number | null;
  artist_id: number | null;
  artist: string | null;
  track_count: number;
  has_cover: boolean;
}

export interface AlbumDetail {
  id: number;
  title: string;
  year: number | null;
  artist_id: number | null;
  artist: string | null;
  has_cover: boolean;
  tracks: Track[];
}

export interface ArtistSummary {
  id: number;
  name: string;
}

export interface SearchResults {
  artists: ArtistSummary[];
  albums: AlbumSummary[];
  tracks: Track[];
}

export interface Stats {
  artists: number;
  albums: number;
  tracks: number;
}

export interface PlaylistSummary {
  id: number;
  name: string;
  track_count: number;
  created_at: string;
  updated_at: string;
}

export interface PlaylistDetail {
  id: number;
  name: string;
  created_at: string;
  updated_at: string;
  tracks: Track[];
}

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function sendJSON<T>(
  url: string,
  method: string,
  body?: unknown
): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      if (data?.detail) detail = data.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  stats: () => getJSON<Stats>("/api/stats"),
  albums: () => getJSON<AlbumSummary[]>("/api/albums"),
  album: (id: number) => getJSON<AlbumDetail>(`/api/albums/${id}`),
  tracks: () => getJSON<Track[]>("/api/tracks"),
  search: (q: string) =>
    getJSON<SearchResults>(`/api/search?q=${encodeURIComponent(q)}`),
  rescan: async (): Promise<Stats> => {
    const res = await fetch("/api/rescan", { method: "POST" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  },
  coverUrl: (albumId: number) => `/api/covers/${albumId}`,
  streamUrl: (trackId: number) => `/api/stream/${trackId}`,

  playlists: () => getJSON<PlaylistSummary[]>("/api/playlists"),
  playlist: (id: number) => getJSON<PlaylistDetail>(`/api/playlists/${id}`),
  createPlaylist: (name: string) =>
    sendJSON<PlaylistDetail>("/api/playlists", "POST", { name }),
  renamePlaylist: (id: number, name: string) =>
    sendJSON<PlaylistDetail>(`/api/playlists/${id}`, "PATCH", { name }),
  deletePlaylist: (id: number) =>
    sendJSON<void>(`/api/playlists/${id}`, "DELETE"),
  addToPlaylist: (id: number, trackId: number) =>
    sendJSON<PlaylistDetail>(`/api/playlists/${id}/tracks`, "POST", {
      track_id: trackId,
    }),
  removeFromPlaylist: (id: number, trackId: number) =>
    sendJSON<PlaylistDetail>(`/api/playlists/${id}/tracks/${trackId}`, "DELETE"),
  reorderPlaylist: (id: number, trackIds: number[]) =>
    sendJSON<PlaylistDetail>(`/api/playlists/${id}/tracks`, "PUT", {
      track_ids: trackIds,
    }),
};
