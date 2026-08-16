export type SyncStatus =
  | "not_connected"
  | "connecting"
  | "connected"
  | "syncing"
  | "fetching_videos"
  | "saving_videos"
  | "indexing_videos"
  | "fetching_comments"
  | "processing_comments"
  | "ready"
  | "failed";

export type PartStatus = "not_connected" | "pending" | "syncing" | "ready" | "failed";

export type Channel = {
  id: number;
  youtube_channel_id: string;
  channel_title: string;
  channel_url: string | null;
  custom_url: string | null;
  thumbnail_url: string | null;
  description: string;
  country: string | null;
  default_language: string | null;
  published_at: string | null;
  uploads_playlist_id: string | null;
  subscriber_count: number;
  hidden_subscriber_count: boolean;
  channel_view_count: number;
  public_video_count: number;
  keywords: string | null;
  topic_categories: string[];
  privacy_status: string | null;
  made_for_kids: boolean | null;
  created_at: string;
  updated_at: string;
};

export type ChannelSync = {
  status: SyncStatus;
  video_sync_status: PartStatus;
  comment_sync_status: PartStatus;
  index_status: PartStatus;
  videos_discovered: number;
  videos_indexed: number;
  comments_imported: number;
  last_video_sync_at: string | null;
  last_comment_sync_at: string | null;
  last_full_sync_at: string | null;
};

export type CurrentChannelResponse = {
  connected: boolean;
  channel: Channel | null;
  sync: ChannelSync | null;
};

export type DashboardMetrics = {
  comments_processed: number;
  questions_detected: number;
  existing_answers_found: number;
  content_requests: number;
  pending_replies: number;
  published_replies: number;
};

export type Analysis = {
  id: number;
  intent: "question" | "content_request" | "complaint" | "feedback" | "praise" | "spam" | "other";
  topic: string;
  sentiment: "positive" | "neutral" | "negative";
  is_question: boolean;
  is_content_request: boolean;
  should_reply: boolean;
  reply_reason: string;
  confidence: number;
  model: string;
  relevance_score: number;
  priority_score: number;
};

export type ReplyStatus =
  | "pending_approval"
  | "approved"
  | "ignored"
  | "publishing"
  | "published"
  | "failed";

export type Reply = {
  id: number;
  comment_id: number;
  suggested_reply: string;
  edited_reply: string | null;
  status: ReplyStatus;
  matched_video_id: number;
  similarity: number;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  published_at: string | null;
  youtube_reply_id: string | null;
};

export type Comment = {
  id: number;
  youtube_comment_id: string;
  youtube_thread_id: string;
  video_id: number;
  author_name: string;
  author_channel_id: string | null;
  author_profile_image_url: string | null;
  author_channel_url: string | null;
  text: string;
  like_count: number;
  reply_count: number;
  can_reply: boolean;
  is_public: boolean;
  published_at: string;
  updated_at: string;
  processing_status: string;
  pipeline_status: string;
  pipeline_outcome: string | null;
  pipeline_started_at: string | null;
  pipeline_completed_at: string | null;
  created_at: string;
  analysis: Analysis | null;
  video: {
    id: number;
    youtube_video_id: string;
    title: string;
    description: string;
  };
  semantic_match: {
    match_found: boolean;
    similarity: number | null;
    video_chunk: {
      text: string;
      start_time: number | null;
      video: {
        id: number;
        youtube_video_id: string;
        title: string;
      };
    } | null;
  } | null;
  reply_suggestion: Reply | null;
};

export type Video = {
  id: number;
  youtube_video_id: string;
  channel_id: string;
  channel_title: string;
  title: string;
  youtube_url: string | null;
  thumbnail_url: string | null;
  description: string;
  tags: string[];
  published_at: string | null;
  duration: string | null;
  definition: string | null;
  caption_available: boolean;
  view_count: number;
  like_count: number;
  comment_count: number;
  created_at: string;
  updated_at: string;
  index_status: string;
  indexed_chunk_count: number;
};

export type ContentBrief = {
  id: number;
  opportunity_id: number;
  suggested_title: string;
  hook: string;
  audience_pain: string;
  why_users_want: string;
  video_outline: string[];
  faqs: string[];
  keywords: string[];
  representative_comments: string[];
  model: string;
  created_at: string;
  updated_at: string;
};

export type Opportunity = {
  id: number;
  cluster_id: number;
  topic: string;
  request_count: number;
  unique_users: number;
  total_engagement: number;
  latest_request_at: string;
  frequency_score: number;
  engagement_score: number;
  recency_score: number;
  unique_users_score: number;
  content_gap_score: number;
  demand_score: number;
  created_at: string;
  updated_at: string;
  content_brief: ContentBrief | null;
  representative_comments: string[];
};
