"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDate, formatNumber } from "@/lib/format";
import type { ContentBrief, Opportunity } from "@/lib/types";
import EmptyState from "@/components/EmptyState";

export default function OpportunitiesPage() {
  const [items, setItems] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState<number | null>(null);

  const load = useCallback(async () => {
    try { setItems(await api<Opportunity[]>("opportunities?limit=100&offset=0")); setError(null); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to load opportunities"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function generateBrief(id: number) {
    setGenerating(id);
    try {
      const brief = await api<ContentBrief>(`opportunities/${id}/brief`, { method: "POST" });
      setItems((current) => current.map((item) => item.id === id ? { ...item, content_brief: brief } : item));
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to generate brief"); }
    finally { setGenerating(null); }
  }

  return (
    <div className="stack-lg">
      <div className="page-intro"><div><span className="section-kicker">Unmet audience demand</span><h2>Turn unanswered requests into the next video.</h2><p>When Gemini says a comment matters but semantic search cannot find a supported answer in the channel library, CreatorLoop clusters the demand and scores the opportunity.</p></div><button className="button secondary" onClick={load}>Refresh</button></div>
      {error && <div className="banner error">{error}</div>}
      {loading ? <div className="loading-panel"><span className="spinner" /> Loading opportunities…</div> : items.length === 0 ? (
        <EmptyState title="No content gaps yet" description="Unanswered content requests will be grouped here as CreatorLoop monitors new comments." />
      ) : (
        <div className="opportunity-list">
          {items.map((item, index) => (
            <article className="opportunity-card card" key={item.id}>
              <div className="opportunity-rank">#{index + 1}</div>
              <div className="opportunity-main">
                <div className="section-heading compact"><div><span className="section-kicker">Demand score {Math.round(item.demand_score)}</span><h3>{item.topic}</h3></div><div className="score-ring">{Math.round(item.demand_score)}</div></div>
                <div className="opportunity-stats"><span><strong>{formatNumber(item.request_count)}</strong> requests</span><span><strong>{formatNumber(item.unique_users)}</strong> viewers</span><span><strong>{formatNumber(item.total_engagement)}</strong> engagement</span><span>Latest {formatDate(item.latest_request_at)}</span></div>
                <div className="representative-comments">{item.representative_comments.slice(0, 3).map((comment, i) => <blockquote key={i}>“{comment}”</blockquote>)}</div>
                {item.content_brief ? (
                  <div className="brief-box"><span className="section-kicker">AI content brief</span><h4>{item.content_brief.suggested_title}</h4><p>{item.content_brief.hook}</p><div className="outline"><strong>Suggested outline</strong><ol>{item.content_brief.video_outline.map((line) => <li key={line}>{line}</li>)}</ol></div><div className="keyword-row">{item.content_brief.keywords.slice(0, 8).map((keyword) => <span key={keyword}>{keyword}</span>)}</div></div>
                ) : <button className="button secondary" disabled={generating === item.id} onClick={() => generateBrief(item.id)}>{generating === item.id ? "Generating with Gemini…" : "Generate content brief"}</button>}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
