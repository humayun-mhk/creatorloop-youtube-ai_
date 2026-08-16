"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDate, formatNumber, titleCase } from "@/lib/format";
import type { Video } from "@/lib/types";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";

export default function VideosPage() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setVideos(await api<Video[]>("videos?limit=100&offset=0")); setError(null); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to load videos"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="stack-lg">
      <div className="page-intro"><div><span className="section-kicker">Creator knowledge base</span><h2>The channel library behind every answer.</h2><p>n8n imports public video metadata. FastAPI indexes title and description into pgvector so suggested replies can be grounded in the creator’s own content.</p></div><button className="button secondary" onClick={load}>Refresh</button></div>
      {error && <div className="banner error">{error}</div>}
      {loading ? <div className="loading-panel"><span className="spinner" /> Loading videos…</div> : videos.length === 0 ? (
        <EmptyState title="Video library is empty" description="Connect a channel and let the full n8n sync import its public uploads." />
      ) : (
        <div className="video-grid">
          {videos.map((video) => (
            <article className="video-card card" key={video.id}>
              <a className="thumbnail" href={video.youtube_url ?? `https://youtube.com/watch?v=${video.youtube_video_id}`} target="_blank" rel="noreferrer">
                {video.thumbnail_url ? <img src={video.thumbnail_url} alt="" /> : <div className="thumbnail-fallback">▶</div>}
                <span>Open ↗</span>
              </a>
              <div className="video-body"><div className="meta-row"><StatusBadge value={video.index_status} /><span>{formatDate(video.published_at)}</span></div><h3>{video.title}</h3><p>{video.description || "No public description."}</p><div className="video-stats"><span>{formatNumber(video.view_count)} views</span><span>{formatNumber(video.like_count)} likes</span><span>{formatNumber(video.comment_count)} comments</span></div><div className="index-line"><span>Vector chunks</span><strong>{formatNumber(video.indexed_chunk_count)}</strong><span>{titleCase(video.definition)}</span></div></div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
