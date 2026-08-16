"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Comment, Reply } from "@/lib/types";
import { formatDate, percent, titleCase } from "@/lib/format";
import StatusBadge from "@/components/StatusBadge";

export default function ReplyCard({ reply, comment, onChange }: { reply: Reply; comment?: Comment; onChange?: (reply: Reply) => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(reply.edited_reply ?? reply.suggested_reply);
  const [busy, setBusy] = useState<"publish" | "ignore" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const act = async (kind: "publish" | "ignore") => {
    setBusy(kind);
    setError(null);
    try {
      const updated = await api<Reply>(`replies/${reply.id}/${kind === "publish" ? "approve" : "ignore"}`, {
        method: "POST",
        body: kind === "publish" ? JSON.stringify({ reply: text.trim() || null }) : undefined,
      });
      onChange?.(updated);
      if (kind === "publish") setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(null);
    }
  };

  const actionable = reply.status === "pending_approval" || reply.status === "failed";

  return (
    <article className="reply-card">
      <div className="reply-card-head">
        <div>
          <div className="meta-row">
            <StatusBadge value={reply.status} />
            <span>{percent(reply.similarity)} match</span>
            <span>{formatDate(reply.created_at)}</span>
          </div>
          <h3>{comment ? `Reply to ${comment.author_name}` : `Reply #${reply.id}`}</h3>
        </div>
      </div>

      {comment && (
        <div className="comment-context">
          <span>Viewer comment</span>
          <p>{comment.text}</p>
          <small>{comment.video.title}</small>
        </div>
      )}

      <div className="reply-editor">
        <label>AI suggested reply</label>
        {editing ? (
          <textarea value={text} onChange={(event) => setText(event.target.value)} maxLength={2000} rows={5} />
        ) : (
          <p>{reply.edited_reply ?? reply.suggested_reply}</p>
        )}
        {editing && <small>{text.length}/2000 characters</small>}
      </div>

      {error && <div className="inline-error">{error}</div>}

      {actionable ? (
        <div className="button-row">
          <button className="button primary" disabled={busy !== null || !text.trim()} onClick={() => act("publish")}>
            {busy === "publish" ? "Publishing…" : "Approve & publish"}
          </button>
          <button className="button secondary" disabled={busy !== null} onClick={() => setEditing((value) => !value)}>
            {editing ? "Cancel edit" : "Edit reply"}
          </button>
          <button className="button ghost danger-text" disabled={busy !== null} onClick={() => act("ignore")}>
            {busy === "ignore" ? "Ignoring…" : "Ignore"}
          </button>
        </div>
      ) : (
        <div className="reply-footnote">{reply.youtube_reply_id ? "Published to YouTube" : titleCase(reply.status)}</div>
      )}
    </article>
  );
}
