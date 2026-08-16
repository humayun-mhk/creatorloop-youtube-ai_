# CreatorLoop Next.js frontend — updated workflow UI

This frontend matches the CreatorLoop FastAPI + n8n architecture updated on 2026-08-16.

## User flow

1. User enters a public YouTube channel handle / URL / channel ID.
2. Browser calls this Next.js app's server proxy.
3. Next.js securely calls FastAPI `POST /api/channels/connect` with `X-Internal-API-Key`.
4. FastAPI invokes the n8n sync workflow and stores channel metadata.
5. Dashboard polls sync status while n8n imports/indexes videos and fetches comments.
6. Comments page displays Gemini `should_reply`, reason, intent, confidence, priority, semantic match and content-gap result.
7. Replies page lets the user edit, ignore, or **Approve & publish** a suggestion.
8. Approve calls FastAPI, which calls the separate n8n YouTube reply publisher.
9. Opportunities page shows unmet demand clusters and can generate an AI content brief.
10. Videos page shows the creator-owned public knowledge library used for grounding.

## Environment

Create `.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
FASTAPI_INTERNAL_API_KEY=the-same-value-as-backend-INTERNAL_API_KEY
```

For Vercel, set the production Render URL in `NEXT_PUBLIC_API_BASE_URL` and the same backend `INTERNAL_API_KEY` value in `FASTAPI_INTERNAL_API_KEY`.

**Do not rename `FASTAPI_INTERNAL_API_KEY` to `NEXT_PUBLIC_FASTAPI_INTERNAL_API_KEY`.** The current design keeps it on the Next.js server only.

## Run

```powershell
npm install
npm run dev
```

Production check:

```powershell
npm run lint
npm run build
```

## Important publishing behavior

The UI says **Approve & publish** because the current FastAPI approval endpoint immediately invokes the n8n `youtube-reply` publisher. It is not a separate approval-only state in the current backend.

## Vercel

Use:

```text
Root Directory: frontend
Framework: Next.js
Install Command: npm install
Build Command: npm run build
Output Directory: leave empty
```

If you replace your existing repo frontend, copy this folder's contents into your repository's existing `frontend/` directory.

## Security boundary

The Next.js server proxy has an endpoint allow-list and only attaches the FastAPI internal secret to protected actions used by the UI. For a public production product, add real user authentication/authorization before allowing arbitrary users to trigger connect, publish, or ignore actions.
