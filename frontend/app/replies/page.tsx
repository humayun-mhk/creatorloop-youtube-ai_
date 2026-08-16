"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Comment, Reply } from "@/lib/types";
import EmptyState from "@/components/EmptyState";
import ReplyCard from "@/components/ReplyCard";

type ReplyFilter = "pending" | "failed" | "published" | "all";

export default function RepliesPage() {
  const [replies, setReplies] = useState<Reply[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ReplyFilter>("pending");

  const load = useCallback(async (showRefreshState = false) => {
    if (showRefreshState) {
      setRefreshing(true);
    }

    try {
      setError(null);

      const [replyData, commentData] = await Promise.all([
        api<Reply[]>("replies?limit=100&offset=0"),
        api<Comment[]>("comments?limit=100&offset=0"),
      ]);

      setReplies(replyData);
      setComments(commentData);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load replies",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const counts = useMemo(
    () => ({
      pending: replies.filter(
        (reply) => reply.status === "pending_approval",
      ).length,
      failed: replies.filter(
        (reply) => reply.status === "failed",
      ).length,
      published: replies.filter(
        (reply) => reply.status === "published",
      ).length,
      all: replies.length,
    }),
    [replies],
  );

  const filtered = useMemo(() => {
    return replies.filter((reply) => {
      if (filter === "all") return true;
      if (filter === "pending") {
        return reply.status === "pending_approval";
      }
      if (filter === "failed") {
        return reply.status === "failed";
      }
      return reply.status === "published";
    });
  }, [replies, filter]);

  const commentsById = useMemo(
    () =>
      new Map(
        comments.map((comment) => [comment.id, comment]),
      ),
    [comments],
  );

  function replaceReply(updated: Reply) {
    setReplies((current) =>
      current.map((reply) =>
        reply.id === updated.id ? updated : reply,
      ),
    );
  }

  const emptyTitle =
    filter === "pending"
      ? "No replies need approval"
      : filter === "failed"
        ? "No failed replies"
        : filter === "published"
          ? "No published replies yet"
          : "No replies found";

  return (
    <div className="stack-lg">
      <div className="page-intro">
        <div>
          <span className="section-kicker">
            Human approval
          </span>
          <h2>Review every reply before it reaches YouTube.</h2>
          <p>
            CreatorLoop generates a reply only when it finds
            supporting creator content. Publishing uses the
            YouTube OAuth account configured in your n8n reply
            workflow.
          </p>
        </div>

        <button
          className="button secondary"
          onClick={() => void load(true)}
          disabled={refreshing}
        >
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="filter-bar">
        <button
          className={filter === "pending" ? "active" : ""}
          onClick={() => setFilter("pending")}
        >
          Needs approval ({counts.pending})
        </button>

        <button
          className={filter === "failed" ? "active" : ""}
          onClick={() => setFilter("failed")}
        >
          Failed ({counts.failed})
        </button>

        <button
          className={filter === "published" ? "active" : ""}
          onClick={() => setFilter("published")}
        >
          Published ({counts.published})
        </button>

        <button
          className={filter === "all" ? "active" : ""}
          onClick={() => setFilter("all")}
        >
          All ({counts.all})
        </button>
      </div>

      <div className="banner info">
        <strong>Approval means publish.</strong>{" "}
        CreatorLoop sends the final approved text through FastAPI
        to the protected n8n YouTube reply workflow. Failed
        publishing attempts remain available here so you can retry
        them.
      </div>

      {error && (
        <div className="banner error">{error}</div>
      )}

      {loading ? (
        <div className="loading-panel">
          <span className="spinner" /> Loading replies…
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          title={emptyTitle}
          description="When CreatorLoop recommends a response and semantic search finds supporting creator content, it will appear here."
        />
      ) : (
        <div className="reply-list">
          {filtered.map((reply) => (
            <div
              id={`reply-${reply.id}`}
              key={reply.id}
            >
              <ReplyCard
                reply={reply}
                comment={commentsById.get(reply.comment_id)}
                onChange={replaceReply}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}