"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatDate, formatNumber, titleCase } from "@/lib/format";
import type {
  Comment,
  CurrentChannelResponse,
  DashboardMetrics,
  Opportunity,
  Reply,
} from "@/lib/types";
import StatusBadge from "@/components/StatusBadge";
import EmptyState from "@/components/EmptyState";

const VIDEO_SYNC_WINDOW = 50;
const COMMENT_SYNC_WINDOW = 20;

const emptyMetrics: DashboardMetrics = {
  comments_processed: 0,
  questions_detected: 0,
  existing_answers_found: 0,
  content_requests: 0,
  pending_replies: 0,
  published_replies: 0,
};

export default function OverviewPage() {
  const [channel, setChannel] = useState<CurrentChannelResponse | null>(null);
  const [metrics, setMetrics] = useState<DashboardMetrics>(emptyMetrics);
  const [comments, setComments] = useState<Comment[]>([]);
  const [replies, setReplies] = useState<Reply[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [target, setTarget] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (silent = false) => {
    try {
      const current = await api<CurrentChannelResponse>("channels/current");
      setChannel(current);

      if (current.connected) {
        const [
          summary,
          recentComments,
          recentReplies,
          recentOpportunities,
        ] = await Promise.all([
          api<DashboardMetrics>("dashboard/summary"),
          api<Comment[]>("comments?limit=5&offset=0"),
          api<Reply[]>("replies?limit=4&offset=0"),
          api<Opportunity[]>("opportunities?limit=4&offset=0"),
        ]);

        setMetrics(summary);
        setComments(recentComments);
        setReplies(recentReplies);
        setOpportunities(recentOpportunities);
      }
    } catch (err) {
      // Background polling should not replace a healthy sync UI with a
      // transient banner. Initial/manual loads still surface real errors.
      if (!silent) {
        setError(
          err instanceof Error ? err.message : "Unable to load CreatorLoop",
        );
      }
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void load();

    const interval = setInterval(() => {
      const status = channel?.sync?.status;

      if (status && status !== "ready" && status !== "failed") {
        void load(true);
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [load, channel?.sync?.status]);

  async function connect(event: FormEvent) {
    event.preventDefault();
    if (!target.trim()) return;

    setConnecting(true);
    setError(null);

    try {
      const result = await api<CurrentChannelResponse>("channels/connect", {
        method: "POST",
        body: JSON.stringify({ target_channel: target.trim() }),
      });

      setChannel(result);
      setTarget("");

      // Refresh dashboard data, but do not turn a successful connection into
      // an error just because one secondary dashboard request is transient.
      void load(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to connect channel",
      );
    } finally {
      setConnecting(false);
    }
  }

  async function syncNow() {
    setSyncing(true);
    setError(null);

    try {
      // FastAPI returns 202 when n8n has accepted the sync. At that point the
      // sync is successfully started; the dashboard can refresh via polling.
      await api("channels/sync", { method: "POST" });

      // Update the UI immediately instead of issuing several secondary API
      // requests and potentially showing a misleading error after a valid 202.
      setChannel((current) => {
        if (!current?.sync) return current;

        return {
          ...current,
          sync: {
            ...current.sync,
            status: "syncing",
            video_sync_status: "pending",
            comment_sync_status: "pending",
            index_status: "pending",
          },
        };
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to start sync",
      );
    } finally {
      setSyncing(false);
    }
  }

  if (loading) {
    return (
      <div className="loading-panel">
        <span className="spinner" /> Loading CreatorLoop…
      </div>
    );
  }

  if (!channel?.connected || !channel.channel) {
    return (
      <section className="connect-layout">
        <div className="connect-copy">
          <span className="section-kicker">Public YouTube intelligence</span>
          <h2>Turn audience comments into answers and content demand.</h2>
          <p>
            Connect any public YouTube channel. CreatorLoop checks the latest{" "}
            {VIDEO_SYNC_WINDOW} videos, incrementally indexes only new or
            changed content, and analyzes up to the latest{" "}
            {COMMENT_SYNC_WINDOW} comments per sync.
          </p>

          <div className="flow-strip">
            <span>YouTube</span>
            <b>→</b>
            <span>n8n</span>
            <b>→</b>
            <span>FastAPI + Gemini</span>
            <b>→</b>
            <span>CreatorLoop</span>
          </div>
        </div>

        <form className="connect-card" onSubmit={connect}>
          <div className="youtube-mark">▶</div>
          <h3>Analyze a YouTube channel</h3>
          <p>Paste a channel handle, channel URL, or public channel ID.</p>

          <label htmlFor="channel">YouTube channel</label>
          <input
            id="channel"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="@codebasics or youtube.com/@codebasics"
            autoComplete="off"
          />

          <button
            className="button primary wide"
            disabled={connecting || !target.trim()}
          >
            {connecting ? "Connecting & starting sync…" : "Connect channel"}
          </button>

          {error && <div className="inline-error">{error}</div>}

          <small>
            Public analysis checks at most {VIDEO_SYNC_WINDOW} recent videos
            and {COMMENT_SYNC_WINDOW} recent comments per sync.
          </small>
        </form>
      </section>
    );
  }

  const c = channel.channel;
  const sync = channel.sync;

  const syncBusy =
    syncing ||
    sync?.status === "connecting" ||
    sync?.status === "syncing" ||
    sync?.status === "fetching_videos" ||
    sync?.status === "saving_videos" ||
    sync?.status === "indexing_videos" ||
    sync?.status === "fetching_comments" ||
    sync?.status === "processing_comments";

  return (
    <div className="stack-lg">
      {error && <div className="banner error">{error}</div>}

      <section className="channel-hero card">
        <div className="channel-profile">
          {c.thumbnail_url ? (
            <img className="channel-avatar" src={c.thumbnail_url} alt="" />
          ) : (
            <div className="channel-avatar fallback">YT</div>
          )}

          <div>
            <div className="meta-row">
              <StatusBadge value={sync?.status} />
              <span>{c.custom_url ?? c.youtube_channel_id}</span>
            </div>

            <h2>{c.channel_title}</h2>
            <p>
              {c.description ||
                "Public YouTube channel connected to CreatorLoop."}
            </p>
          </div>
        </div>

        <div className="hero-actions">
          <button
            type="button"
            className="button secondary"
            onClick={syncNow}
            disabled={syncBusy}
          >
            {syncBusy ? "Syncing…" : "Sync latest"}
          </button>

          <a
            className="button ghost"
            href={
              c.channel_url ??
              `https://youtube.com/channel/${c.youtube_channel_id}`
            }
            target="_blank"
            rel="noreferrer"
          >
            Open YouTube ↗
          </a>
        </div>

        <div className="channel-stats">
          <div>
            <span>Subscribers</span>
            <strong>
              {c.hidden_subscriber_count
                ? "Hidden"
                : formatNumber(c.subscriber_count)}
            </strong>
          </div>

          <div>
            <span>Channel views</span>
            <strong>{formatNumber(c.channel_view_count)}</strong>
          </div>

          <div>
            <span>Public videos</span>
            <strong>{formatNumber(c.public_video_count)}</strong>
          </div>

          <div>
            <span>Country</span>
            <strong>{c.country ?? "—"}</strong>
          </div>

          <div>
            <span>Video sync window</span>
            <strong>Latest {VIDEO_SYNC_WINDOW}</strong>
          </div>

          <div>
            <span>Comment sync window</span>
            <strong>Latest {COMMENT_SYNC_WINDOW}</strong>
          </div>
        </div>
      </section>

      {sync && sync.status !== "ready" && (
        <section className="sync-card card">
          <div className="section-heading compact">
            <div>
              <span className="section-kicker">Live pipeline</span>
              <h3>Building channel intelligence</h3>
            </div>
            <StatusBadge value={sync.status} />
          </div>

          <div className="pipeline-grid">
            <PipelineStep
              title="Videos"
              status={sync.video_sync_status}
              value={`latest ${VIDEO_SYNC_WINDOW} checked · ${formatNumber(
                sync.videos_discovered,
              )} stored`}
            />

            <PipelineStep
              title="Vector index"
              status={sync.index_status}
              value={`${formatNumber(
                sync.videos_indexed,
              )} indexed · unchanged videos reused`}
            />

            <PipelineStep
              title="Comments"
              status={sync.comment_sync_status}
              value={`latest ${COMMENT_SYNC_WINDOW} checked · ${formatNumber(
                sync.comments_imported,
              )} total stored`}
            />
          </div>
        </section>
      )}

      <section className="metric-grid">
        <Metric
          label="Comments processed"
          value={metrics.comments_processed}
          note="Gemini evaluated"
        />
        <Metric
          label="Questions detected"
          value={metrics.questions_detected}
          note="Audience questions"
        />
        <Metric
          label="Existing answers"
          value={metrics.existing_answers_found}
          note="Video match found"
        />
        <Metric
          label="Content requests"
          value={metrics.content_requests}
          note="Potential demand"
        />
        <Metric
          label="Pending replies"
          value={metrics.pending_replies}
          note="Need your approval"
          accent
        />
        <Metric
          label="Published replies"
          value={metrics.published_replies}
          note="Sent through n8n"
        />
      </section>

      <section className="two-column">
        <div className="card panel">
          <div className="section-heading">
            <div>
              <span className="section-kicker">Latest analysis</span>
              <h3>Recent comments</h3>
            </div>
            <Link href="/comments" className="text-link">
              View all →
            </Link>
          </div>

          {comments.length ? (
            <div className="list-stack">
              {comments.map((comment) => (
                <Link
                  href={`/comments#comment-${comment.id}`}
                  className="comment-list-item"
                  key={comment.id}
                >
                  <div className="avatar-small">
                    {comment.author_name.slice(0, 1).toUpperCase()}
                  </div>

                  <div className="grow">
                    <div className="row-between">
                      <strong>{comment.author_name}</strong>
                      <small>{formatDate(comment.published_at)}</small>
                    </div>

                    <p>{comment.text}</p>

                    <div className="meta-row">
                      <span>
                        {comment.analysis
                          ? titleCase(comment.analysis.intent)
                          : titleCase(comment.processing_status)}
                      </span>

                      {comment.analysis?.should_reply && (
                        <span className="positive-text">
                          Reply recommended
                        </span>
                      )}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No comments yet"
              description={`CreatorLoop checks up to the latest ${COMMENT_SYNC_WINDOW} public comments on each channel sync.`}
            />
          )}
        </div>

        <div className="card panel">
          <div className="section-heading">
            <div>
              <span className="section-kicker">Action queue</span>
              <h3>Replies & demand</h3>
            </div>
            <Link href="/replies" className="text-link">
              Review replies →
            </Link>
          </div>

          <div className="mini-summary">
            <span>Pending AI replies</span>
            <strong>
              {
                replies.filter(
                  (reply) => reply.status === "pending_approval",
                ).length
              }
            </strong>
          </div>

          <div className="mini-summary">
            <span>Content opportunities</span>
            <strong>{opportunities.length}</strong>
          </div>

          <div className="mini-summary">
            <span>Last video sync</span>
            <strong className="small-strong">
              {formatDate(sync?.last_video_sync_at)}
            </strong>
          </div>

          <div className="mini-summary">
            <span>Last comment sync</span>
            <strong className="small-strong">
              {formatDate(sync?.last_comment_sync_at)}
            </strong>
          </div>

          <div className="callout">
            <span>Incremental sync</span>
            <p>
              n8n checks the latest {VIDEO_SYNC_WINDOW} videos and latest{" "}
              {COMMENT_SYNC_WINDOW} comments. FastAPI reuses already indexed
              videos and only embeds new, changed, or missing-index content.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

function Metric({
  label,
  value,
  note,
  accent = false,
}: {
  label: string;
  value: number;
  note: string;
  accent?: boolean;
}) {
  return (
    <div className={`metric-card ${accent ? "accent" : ""}`}>
      <span>{label}</span>
      <strong>{formatNumber(value)}</strong>
      <small>{note}</small>
    </div>
  );
}

function PipelineStep({
  title,
  status,
  value,
}: {
  title: string;
  status: string;
  value: string;
}) {
  return (
    <div className="pipeline-step">
      <div
        className={`step-dot ${
          status === "ready"
            ? "done"
            : status === "failed"
              ? "failed"
              : "working"
        }`}
      />
      <div>
        <strong>{title}</strong>
        <span>
          {titleCase(status)} · {value}
        </span>
      </div>
    </div>
  );
}
