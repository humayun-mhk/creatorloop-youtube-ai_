# CreatorLoop full stack v3

Contents:
- `frontend/` — Next.js App Router UI matched to the updated FastAPI contracts
- `backend/` — updated FastAPI backend with Gemini reply decision and public-channel metadata
- `creatorloop-youtube-sync-monitor.json` — public YouTube sync + 15-minute comment monitor
- `creatorloop-youtube-publish-reply.json` — separate YouTube OAuth reply publisher

Deployment order:
1. Deploy backend and run `alembic upgrade head`.
2. Import/remap/activate both n8n workflows.
3. Configure backend n8n/Gemini/internal secrets.
4. Put the `frontend/` folder at your Vercel Root Directory `frontend`.
5. Configure frontend `NEXT_PUBLIC_API_BASE_URL` and server-only `FASTAPI_INTERNAL_API_KEY`.
6. Deploy frontend.
7. Connect a public YouTube channel from the CreatorLoop dashboard.
