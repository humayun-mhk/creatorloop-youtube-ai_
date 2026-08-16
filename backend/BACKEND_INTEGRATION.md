# Backend changes for the CreatorLoop n8n split

This backend matches the two n8n workflows:

1. `creatorloop-channel-sync` — public YouTube read/sync + scheduled comment monitor.
2. `youtube-reply` — OAuth publishing only after approval.

## Backend-owned flow

`POST /api/channels/connect`
→ FastAPI asks n8n to resolve the public channel
→ FastAPI stores the returned channel identity
→ FastAPI starts the full n8n sync.

n8n callbacks:

- `POST /api/channels/{channel_id}/internal/videos` stores and indexes video batches.
- `POST /api/channels/{channel_id}/internal/progress` updates sync state.
- `POST /api/youtube/comments/ingest` stores each comment and immediately executes the AI pipeline.

AI processing inside FastAPI:

1. Gemini classifies intent/topic/sentiment and returns `should_reply` + `reply_reason`.
2. If no reply is needed, processing ends as `no_reply_needed`.
3. If a reply is useful, semantic search checks the connected channel's indexed videos.
4. If supporting content exists, FastAPI creates a pending reply suggestion.
5. If no supporting content exists, the request is treated as unmet demand/content opportunity.

Publishing:

`POST /api/replies/{reply_id}/approve`
→ FastAPI marks the reply as publishing
→ FastAPI calls the separate `youtube-reply` n8n webhook
→ n8n publishes using its YouTube OAuth credential
→ FastAPI stores the returned YouTube reply id and marks the suggestion `published`.

## Database migrations

Run Alembic through head before using this version. The new revisions are:

- `20260816_0013_channel_public_metadata.py`
- `20260816_0014_comment_reply_decision.py`

## Important secrets

Use separate values for:

- `INTERNAL_API_KEY`: n8n -> FastAPI comment ingestion.
- `N8N_CHANNEL_SYNC_WEBHOOK_SECRET`: FastAPI -> sync webhook and n8n -> protected sync callback endpoints.
- `N8N_REPLY_WEBHOOK_SECRET`: FastAPI -> publishing webhook.

Do not expose these secrets in browser-side `NEXT_PUBLIC_*` variables.
