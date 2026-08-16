import { titleCase } from "@/lib/format";

export default function StatusBadge({ value }: { value: string | null | undefined }) {
  const normalized = value ?? "unknown";
  const tone = ["ready", "published", "completed", "approved"].includes(normalized)
    ? "success"
    : ["failed", "error", "ignored"].includes(normalized)
      ? "danger"
      : ["syncing", "processing", "publishing", "pending_approval", "pending", "fetching_comments", "fetching_videos", "indexing_videos"].includes(normalized)
        ? "warning"
        : "neutral";

  return <span className={`badge ${tone}`}>{titleCase(normalized)}</span>;
}
