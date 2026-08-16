"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { CurrentChannelResponse } from "@/lib/types";
import { titleCase } from "@/lib/format";

const navItems = [
  { href: "/", label: "Overview", glyph: "⌂" },
  { href: "/comments", label: "Comments", glyph: "◌" },
  { href: "/replies", label: "Replies", glyph: "↗" },
  { href: "/opportunities", label: "Opportunities", glyph: "✦" },
  { href: "/videos", label: "Videos", glyph: "▷" },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [channel, setChannel] = useState<CurrentChannelResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await api<CurrentChannelResponse>("channels/current");
        if (!cancelled) setChannel(data);
      } catch {}
    };
    load();
    const interval = setInterval(load, 10000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [pathname]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/" className="brand" aria-label="CreatorLoop home">
          <span className="brand-mark">CL</span>
          <span>
            <strong>CreatorLoop</strong>
            <small>Audience intelligence</small>
          </span>
        </Link>

        <nav className="nav-list" aria-label="Primary navigation">
          {navItems.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link key={item.href} href={item.href} className={`nav-item ${active ? "active" : ""}`}>
                <span className="nav-glyph">{item.glyph}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-channel">
          <span className={`status-dot ${channel?.sync?.status === "failed" ? "danger" : channel?.sync?.status === "ready" ? "ready" : ""}`} />
          <div>
            <small>{channel?.connected ? "Monitored channel" : "No channel connected"}</small>
            <strong>{channel?.channel?.channel_title ?? "Connect YouTube"}</strong>
            {channel?.sync && <span>{titleCase(channel.sync.status)}</span>}
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <span className="eyebrow">CreatorLoop</span>
            <h1>{navItems.find((item) => (item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)))?.label ?? "Dashboard"}</h1>
          </div>
          {channel?.channel && (
            <a className="channel-chip" href={channel.channel.channel_url ?? `https://youtube.com/channel/${channel.channel.youtube_channel_id}`} target="_blank" rel="noreferrer">
              {channel.channel.thumbnail_url ? <img src={channel.channel.thumbnail_url} alt="" /> : <span className="avatar-fallback">YT</span>}
              <span>{channel.channel.channel_title}</span>
              <b>↗</b>
            </a>
          )}
        </header>
        <div className="page-container">{children}</div>
      </main>
    </div>
  );
}
