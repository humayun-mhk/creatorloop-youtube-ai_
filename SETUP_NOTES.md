# CreatorLoop updated architecture

## Flow

1. Frontend sends a public YouTube channel/handle/URL to FastAPI `POST /api/channels/connect`.
2. FastAPI calls the n8n production webhook `creatorloop-channel-sync` with `action=connect`.
3. n8n resolves the public channel and returns rich public channel metadata.
4. FastAPI stores the channel and calls the same n8n webhook with `action=sync`.
5. n8n enumerates the uploads playlist with pagination, fetches video metadata in batches of 50, and sends those batches to FastAPI for storage/indexing.
6. The same n8n workflow polls the channel every 15 minutes. It refreshes recent video metadata, fetches recent channel comment threads, and sends each comment to FastAPI.
7. `POST /api/youtube/comments/ingest` is now the single ingestion + AI processing boundary. FastAPI persists the comment, calls Gemini to classify it and decide `should_reply`, runs semantic search, and creates a reply suggestion when creator-owned content supports an answer. If no supporting answer exists, it becomes unmet demand/content opportunity.
8. Reply approval stays in FastAPI. Only an approved reply calls the second n8n workflow (`youtube-reply`), which publishes with YouTube OAuth.

## n8n imports

Import these as two separate workflows:

- `creatorloop-youtube-sync-monitor.json`
- `creatorloop-youtube-publish-reply.json`

After import, verify/remap these credentials in n8n:

- Public YouTube read API credential: `N8N_QUICK_ANALYZE`
- FastAPI sync webhook credential: `CreatorLoop Channel Sync Auth`
- FastAPI internal ingestion credential: `Header Auth account`
- YouTube OAuth publishing credential: `YouTube account`

Activate both workflows. The schedule trigger uses workflow static data populated after the FastAPI connect/sync call, so connect a channel once after activating the updated workflow.

## FastAPI environment

Keep/set:

- `N8N_CHANNEL_SYNC_WEBHOOK_URL` = production URL for `/webhook/creatorloop-channel-sync`
- `N8N_CHANNEL_SYNC_WEBHOOK_SECRET` = same value configured on that n8n webhook Header Auth credential
- `N8N_REPLY_WEBHOOK_URL` = production URL for `/webhook/youtube-reply`
- `N8N_REPLY_WEBHOOK_SECRET` = same value configured on the reply webhook Header Auth credential
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `INTERNAL_API_KEY` = same secret sent by the n8n FastAPI ingestion credential

Optional reply behavior is controlled by `COMMENT_REPLY_POLICY` (Pydantic settings env name follows the field name in your project settings convention).

## Database

Two new Alembic revisions were added:

- `20260816_0013_channel_public_metadata.py`
- `20260816_0014_comment_reply_decision.py`

Run your project's normal Alembic `upgrade head` deployment step before using the new backend.

## Important public-data boundary

This design analyzes another creator's PUBLIC channel. API-key reads can collect public channel/video/comment data. Private videos, owner analytics, private moderation data, and publishing as that creator are not available without that creator's OAuth authorization. The separate publisher posts using whichever YouTube account is connected to the `YouTube account` OAuth credential.
