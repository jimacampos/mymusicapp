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

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
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
};
