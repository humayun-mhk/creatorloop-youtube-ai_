"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Comment, Reply } from "@/lib/types";
import {
  formatDate,
  percent,
  titleCase,
} from "@/lib/format";
import StatusBadge from "@/components/StatusBadge";

type BusyAction = "publish" | "ignore" | null;

export default function ReplyCard({
  reply,
  comment,
  onChange,
}: {
  reply: Reply;
  comment?: Comment;
  onChange?: (reply: Reply) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(
    reply.edited_reply ?? reply.suggested_reply,
  );
  const [busy, setBusy] =
    useState<BusyAction>(null);
  const [error, setError] =
    useState<string | null>(null);

  const savedReplyText =
    reply.edited_reply ?? reply.suggested_reply;

  useEffect(() => {
    setText(savedReplyText);
  }, [reply.id, savedReplyText]);

  const isPending =
    reply.status === "pending_approval";
  const isFailed = reply.status === "failed";
  const isPublished =
    reply.status === "published";
  const actionable = isPending || isFailed;

  const trimmedText = text.trim();
  const hasChanged =
    trimmedText !== savedReplyText.trim();

  const primaryLabel = useMemo(() => {
    if (busy === "publish") {
      return isFailed ? "Retrying…" : "Publishing…";
    }

    if (editing) {
      return isFailed
        ? "Save & retry"
        : "Save & publish";
    }

    return isFailed
      ? "Retry publish"
      : "Approve & publish";
  }, [busy, editing, isFailed]);

  async function publish() {
    if (!trimmedText) return;

    setBusy("publish");
    setError(null);

    try {
      const updated = await api<Reply>(
        `replies/${reply.id}/approve`,
        {
          method: "POST",
          body: JSON.stringify({
            reply: trimmedText,
          }),
        },
      );

      onChange?.(updated);
      setEditing(false);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Publishing failed",
      );
    } finally {
      setBusy(null);
    }
  }

  async function ignore() {
    setBusy("ignore");
    setError(null);

    try {
      const updated = await api<Reply>(
        `replies/${reply.id}/ignore`,
        {
          method: "POST",
        },
      );

      onChange?.(updated);
      setEditing(false);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to ignore reply",
      );
    } finally {
      setBusy(null);
    }
  }

  function cancelEdit() {
    setText(savedReplyText);
    setEditing(false);
    setError(null);
  }

  return (
    <article className="reply-card">
      <div className="reply-card-head">
        <div>
          <div className="meta-row">
            <StatusBadge value={reply.status} />
            <span>
              {percent(reply.similarity)} match
            </span>
            <span>{formatDate(reply.created_at)}</span>
          </div>

          <h3>
            {comment
              ? `Reply to ${comment.author_name}`
              : `Reply #${reply.id}`}
          </h3>
        </div>
      </div>

      {comment && (
        <div className="comment-context">
          <span>Viewer comment</span>
          <p>{comment.text}</p>

          <small>
            {comment.video?.title ??
              "Source video unavailable"}
          </small>
        </div>
      )}

      <div className="reply-editor">
        <label>
          {reply.edited_reply
            ? "Final reply text"
            : "AI suggested reply"}
        </label>

        {editing ? (
          <>
            <textarea
              value={text}
              onChange={(event) =>
                setText(event.target.value)
              }
              maxLength={2000}
              rows={5}
              autoFocus
            />

            <small>
              {text.length}/2000 characters
              {hasChanged ? " · Edited" : ""}
            </small>
          </>
        ) : (
          <p>{savedReplyText}</p>
        )}
      </div>

      {isFailed && !error && (
        <div className="inline-error">
          Publishing failed previously. You can retry the
          same reply, edit it first, or ignore it.
        </div>
      )}

      {error && (
        <div className="inline-error">{error}</div>
      )}

      {actionable ? (
        <div className="button-row">
          <button
            className="button primary"
            disabled={
              busy !== null || !trimmedText
            }
            onClick={() => void publish()}
          >
            {primaryLabel}
          </button>

          {editing ? (
            <button
              className="button secondary"
              disabled={busy !== null}
              onClick={cancelEdit}
            >
              Cancel edit
            </button>
          ) : (
            <button
              className="button secondary"
              disabled={busy !== null}
              onClick={() => {
                setEditing(true);
                setError(null);
              }}
            >
              {isFailed
                ? "Edit & retry"
                : "Edit reply"}
            </button>
          )}

          <button
            className="button ghost danger-text"
            disabled={busy !== null}
            onClick={() => void ignore()}
          >
            {busy === "ignore"
              ? "Ignoring…"
              : "Ignore"}
          </button>
        </div>
      ) : (
        <div className="reply-footnote">
          {isPublished
            ? reply.youtube_reply_id
              ? "Published to YouTube ✓"
              : "Published ✓"
            : titleCase(reply.status)}
        </div>
      )}
    </article>
  );
}