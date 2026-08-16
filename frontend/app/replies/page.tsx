"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Comment, Reply } from "@/lib/types";
import EmptyState from "@/components/EmptyState";
import ReplyCard from "@/components/ReplyCard";

export default function RepliesPage() {
  const [replies, setReplies] = useState<Reply[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"pending" | "published" | "all">("pending");

  const load = useCallback(async () => {
    try {
      setError(null);
      const [replyData, commentData] = await Promise.all([
        api<Reply[]>("replies?limit=100&offset=0"),
        api<Comment[]>("comments?limit=100&offset=0"),
      ]);
      setReplies(replyData);
      setComments(commentData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load replies");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => replies.filter((reply) => filter === "all" || (filter === "pending" ? ["pending_approval", "failed"].includes(reply.status) : reply.status === "published")), [replies, filter]);
  const commentsById = useMemo(() => new Map(comments.map((comment) => [comment.id, comment])), [comments]);

  function replaceReply(updated: Reply) {
    setReplies((current) => current.map((reply) => reply.id === updated.id ? updated : reply));
  }

  return (
    <div className="stack-lg">
      <div className="page-intro">
        <div><span className="section-kicker">Human approval</span><h2>Review before anything reaches YouTube.</h2><p>Gemini creates a reply only when CreatorLoop finds supporting creator content. Approving a reply immediately calls FastAPI → the separate n8n publisher → YouTube.</p></div>
        <button className="button secondary" onClick={load}>Refresh</button>
      </div>

      <div className="filter-bar">
        <button className={filter === "pending" ? "active" : ""} onClick={() => setFilter("pending")}>Needs approval ({replies.filter((r) => ["pending_approval", "failed"].includes(r.status)).length})</button>
        <button className={filter === "published" ? "active" : ""} onClick={() => setFilter("published")}>Published</button>
        <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>All</button>
      </div>

      <div className="banner info"><strong>Approval means publish.</strong> The backend sends approved text to your `youtube-reply` n8n workflow using the YouTube OAuth account configured there.</div>
      {error && <div className="banner error">{error}</div>}
      {loading ? <div className="loading-panel"><span className="spinner" /> Loading replies…</div> : filtered.length === 0 ? (
        <EmptyState title={filter === "pending" ? "No replies need approval" : "No replies found"} description="When Gemini recommends a response and semantic search finds a supported answer, it will appear here." />
      ) : (
        <div className="reply-list">
          {filtered.map((reply) => <div id={`reply-${reply.id}`} key={reply.id}><ReplyCard reply={reply} comment={commentsById.get(reply.comment_id)} onChange={replaceReply} /></div>)}
        </div>
      )}
    </div>
  );
}
