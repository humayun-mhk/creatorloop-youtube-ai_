"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatDate, formatNumber, titleCase } from "@/lib/format";
import type { Comment, CurrentChannelResponse, DashboardMetrics, Opportunity, Reply } from "@/lib/types";
import StatusBadge from "@/components/StatusBadge";
import EmptyState from "@/components/EmptyState";

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

  const load = useCallback(async () => {
    try {
      const current = await api<CurrentChannelResponse>("channels/current");
      setChannel(current);
      if (current.connected) {
        const [summary, recentComments, recentReplies, recentOpportunities] = await Promise.all([
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
      setError(err instanceof Error ? err.message : "Unable to load CreatorLoop");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(() => {
      if (channel?.sync?.status && channel.sync.status !== "ready" && channel.sync.status !== "failed") load();
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
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to connect channel");
    } finally {
      setConnecting(false);
    }
  }

  async function syncNow() {
    setSyncing(true);
    setError(null);
    try {
      await api("channels/sync", { method: "POST" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start sync");
    } finally {
      setSyncing(false);
    }
  }

  if (loading) return <div className="loading-panel"><span className="spinner" /> Loading CreatorLoop…</div>;

  if (!channel?.connected || !channel.channel) {
    return (
      <section className="connect-layout">
        <div className="connect-copy">
          <span className="section-kicker">Public YouTube intelligence</span>
          <h2>Turn audience comments into answers and content demand.</h2>
          <p>Connect any public YouTube channel. CreatorLoop imports its public video library, monitors new comments, lets Gemini decide which deserve a response, and surfaces content gaps.</p>
          <div className="flow-strip">
            <span>YouTube</span><b>→</b><span>n8n</span><b>→</b><span>FastAPI + Gemini</span><b>→</b><span>CreatorLoop</span>
          </div>
        </div>
        <form className="connect-card" onSubmit={connect}>
          <div className="youtube-mark">▶</div>
          <h3>Analyze a YouTube channel</h3>
          <p>Paste a channel handle, channel URL, or public channel ID.</p>
          <label htmlFor="channel">YouTube channel</label>
          <input id="channel" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="@codebasics or youtube.com/@codebasics" autoComplete="off" />
          <button className="button primary wide" disabled={connecting || !target.trim()}>
            {connecting ? "Connecting & starting sync…" : "Connect channel"}
          </button>
          {error && <div className="inline-error">{error}</div>}
          <small>Only public channel, video, and comment data is read during analysis.</small>
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
          {c.thumbnail_url ? <img className="channel-avatar" src={c.thumbnail_url} alt="" /> : <div className="channel-avatar fallback">YT</div>}
          <div>
            <div className="meta-row"><StatusBadge value={sync?.status} /> <span>{c.custom_url ?? c.youtube_channel_id}</span></div>
            <h2>{c.channel_title}</h2>
            <p>{c.description || "Public YouTube channel connected to CreatorLoop."}</p>
          </div>
        </div>
        <div className="hero-actions">
          
  <button
            type="button"
            className="button secondary"
            onClick={syncNow}
            disabled={syncBusy}
          >
            {syncBusy ? "Syncing…" : "Sync now"}
          </button>
          <a className="button ghost" href={c.channel_url ?? `https://youtube.com/channel/${c.youtube_channel_id}`} target="_blank" rel="noreferrer">Open YouTube ↗</a>
        </div>
        <div className="channel-stats">
          <div><span>Subscribers</span><strong>{c.hidden_subscriber_count ? "Hidden" : formatNumber(c.subscriber_count)}</strong></div>
          <div><span>Channel views</span><strong>{formatNumber(c.channel_view_count)}</strong></div>
          <div><span>Public videos</span><strong>{formatNumber(c.public_video_count)}</strong></div>
          <div><span>Country</span><strong>{c.country ?? "—"}</strong></div>
        </div>
      </section>

      {sync && sync.status !== "ready" && (
        <section className="sync-card card">
          <div className="section-heading compact">
            <div><span className="section-kicker">Live pipeline</span><h3>Building channel intelligence</h3></div>
            <StatusBadge value={sync.status} />
          </div>
          <div className="pipeline-grid">
            <PipelineStep title="Videos" status={sync.video_sync_status} value={`${formatNumber(sync.videos_discovered)} discovered`} />
            <PipelineStep title="Vector index" status={sync.index_status} value={`${formatNumber(sync.videos_indexed)} indexed`} />
            <PipelineStep title="Comments" status={sync.comment_sync_status} value={`${formatNumber(sync.comments_imported)} imported`} />
          </div>
        </section>
      )}

      <section className="metric-grid">
        <Metric label="Comments processed" value={metrics.comments_processed} note="Gemini evaluated" />
        <Metric label="Questions detected" value={metrics.questions_detected} note="Audience questions" />
        <Metric label="Existing answers" value={metrics.existing_answers_found} note="Video match found" />
        <Metric label="Content requests" value={metrics.content_requests} note="Potential demand" />
        <Metric label="Pending replies" value={metrics.pending_replies} note="Need your approval" accent />
        <Metric label="Published replies" value={metrics.published_replies} note="Sent through n8n" />
      </section>

      <section className="two-column">
        <div className="card panel">
          <div className="section-heading">
            <div><span className="section-kicker">Latest analysis</span><h3>Recent comments</h3></div>
            <Link href="/comments" className="text-link">View all →</Link>
          </div>
          {comments.length ? (
            <div className="list-stack">
              {comments.map((comment) => (
                <Link href={`/comments#comment-${comment.id}`} className="comment-list-item" key={comment.id}>
                  <div className="avatar-small">{comment.author_name.slice(0, 1).toUpperCase()}</div>
                  <div className="grow">
                    <div className="row-between"><strong>{comment.author_name}</strong><small>{formatDate(comment.published_at)}</small></div>
                    <p>{comment.text}</p>
                    <div className="meta-row"><span>{comment.analysis ? titleCase(comment.analysis.intent) : titleCase(comment.processing_status)}</span>{comment.analysis?.should_reply && <span className="positive-text">Reply recommended</span>}</div>
                  </div>
                </Link>
              ))}
            </div>
          ) : <EmptyState title="No comments yet" description="New public comments will appear after the channel sync runs." />}
        </div>

        <div className="card panel">
          <div className="section-heading">
            <div><span className="section-kicker">Action queue</span><h3>Replies & demand</h3></div>
            <Link href="/replies" className="text-link">Review replies →</Link>
          </div>
          <div className="mini-summary"><span>Pending AI replies</span><strong>{replies.filter((r) => r.status === "pending_approval").length}</strong></div>
          <div className="mini-summary"><span>Content opportunities</span><strong>{opportunities.length}</strong></div>
          <div className="mini-summary"><span>Last comment sync</span><strong className="small-strong">{formatDate(sync?.last_comment_sync_at)}</strong></div>
          <div className="callout">
            <span>Automation</span>
            <p>n8n checks the monitored channel every 15 minutes. Gemini analysis happens inside FastAPI.</p>
          </div>
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value, note, accent = false }: { label: string; value: number; note: string; accent?: boolean }) {
  return <div className={`metric-card ${accent ? "accent" : ""}`}><span>{label}</span><strong>{formatNumber(value)}</strong><small>{note}</small></div>;
}

function PipelineStep({ title, status, value }: { title: string; status: string; value: string }) {
  return <div className="pipeline-step"><div className={`step-dot ${status === "ready" ? "done" : status === "failed" ? "failed" : "working"}`} /> <div><strong>{title}</strong><span>{titleCase(status)} · {value}</span></div></div>;
}