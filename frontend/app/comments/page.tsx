"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { formatDate, percent, titleCase } from "@/lib/format";
import type { Comment } from "@/lib/types";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";

export default function CommentsPage() {
  const [comments, setComments] = useState<Comment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "reply" | "demand" | "ignored">("all");

  const load = useCallback(async () => {
    try {
      setError(null);
      setComments(await api<Comment[]>("comments?limit=100&offset=0"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load comments");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => comments.filter((comment) => {
    if (filter === "reply") return comment.analysis?.should_reply === true && !!comment.reply_suggestion;
    if (filter === "demand") return comment.pipeline_outcome === "unmet_demand" || (comment.analysis?.is_content_request && !comment.semantic_match?.match_found);
    if (filter === "ignored") return comment.analysis?.should_reply === false;
    return true;
  }), [comments, filter]);

  return (
    <div className="stack-lg">
      <div className="page-intro">
        <div><span className="section-kicker">Gemini decisions</span><h2>Understand every useful audience signal.</h2><p>Comments are collected by n8n and evaluated in FastAPI. CreatorLoop shows why Gemini recommends a reply, the semantic match, and content gaps.</p></div>
        <button className="button secondary" onClick={load}>Refresh</button>
      </div>

      <div className="filter-bar">
        {(["all", "reply", "demand", "ignored"] as const).map((item) => (
          <button key={item} className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>
            {item === "all" ? "All comments" : item === "reply" ? "Reply recommended" : item === "demand" ? "Content demand" : "No reply needed"}
          </button>
        ))}
      </div>

      {error && <div className="banner error">{error}</div>}
      {loading ? <div className="loading-panel"><span className="spinner" /> Loading comments…</div> : filtered.length === 0 ? (
        <EmptyState title="No comments in this view" description="Try another filter or wait for the next n8n comment poll." />
      ) : (
        <div className="comment-grid">
          {filtered.map((comment) => (
            <article className="comment-card card" id={`comment-${comment.id}`} key={comment.id}>
              <div className="comment-card-top">
                <div className="author-row">
                  {comment.author_profile_image_url ? <img src={comment.author_profile_image_url} alt="" /> : <div className="avatar-small">{comment.author_name.slice(0, 1).toUpperCase()}</div>}
                  <div><strong>{comment.author_name}</strong><span>{formatDate(comment.published_at)}</span></div>
                </div>
                <StatusBadge value={comment.pipeline_outcome ?? comment.processing_status} />
              </div>
              <p className="comment-text">{comment.text}</p>
              <a className="video-context" href={`https://youtube.com/watch?v=${comment.video.youtube_video_id}`} target="_blank" rel="noreferrer"><span>▷</span><div><small>Video</small><strong>{comment.video.title}</strong></div><b>↗</b></a>

              {comment.analysis ? (
                <div className="analysis-box">
                  <div className="analysis-head"><span>Gemini analysis</span><strong>{comment.analysis.should_reply ? "Reply recommended" : "No reply needed"}</strong></div>
                  <div className="analysis-tags"><span>{titleCase(comment.analysis.intent)}</span><span>{titleCase(comment.analysis.sentiment)}</span><span>{Math.round(comment.analysis.confidence * 100)}% confidence</span><span>Priority {Math.round(comment.analysis.priority_score)}</span></div>
                  <p>{comment.analysis.reply_reason}</p>
                  <div className="topic-line"><small>Topic</small><strong>{comment.analysis.topic}</strong></div>
                </div>
              ) : <div className="muted-box">Gemini analysis is not available yet.</div>}

              {comment.semantic_match && (
                <div className={`match-box ${comment.semantic_match.match_found ? "found" : "gap"}`}>
                  <div><small>Creator knowledge match</small><strong>{comment.semantic_match.match_found ? `${percent(comment.semantic_match.similarity)} match` : "No supported answer found"}</strong></div>
                  {comment.semantic_match.video_chunk?.video && <span>{comment.semantic_match.video_chunk.video.title}</span>}
                </div>
              )}

              {comment.reply_suggestion && <a className="text-link" href={`/replies#reply-${comment.reply_suggestion.id}`}>Review suggested reply →</a>}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
