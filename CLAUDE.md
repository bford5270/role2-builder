# CLAUDE.md — role2-builder

Context for Claude Code sessions on this repo.

## What this is

Role2 Builder: Next.js frontend (Vercel, `www.role2builder.org`) +
FastAPI backend (`backend/`, served at `https://api.role2builder.org`).
Companion project to **R2RA** (`bford5270/R2RA`) — the Role 2 readiness
assessment app. Scenario cases built here are exported/uploaded into
R2RA assessments.

## Deployment — read before touching Dockerfile, buildspec, or backend

**This repo has no server of its own.** The backend runs as a Docker
Compose co-tenant on R2RA's Elastic Beanstalk instance. Full
architecture, the runtime contract (port 8000; env vars `CORS_ORIGINS`
+ `GEMINI_API_KEY` only; no DATABASE_URL), and the rollback path are in
**README.md § Deployment Architecture** — treat that section as
authoritative and keep it current.

Deploys are fully automatic: push to `main` → GitHub Actions
(`.github/workflows/deploy.yml`, OIDC) → `role2-builder` pipeline
publishes the bundle to S3 → EventBridge rule `rb-publish-chains-r2ra`
starts the `r2ra` pipeline → live in ~15 min. Docs/markdown-only pushes
deliberately do not deploy.

**Never change** the buildspec artifact shape (Dockerfile,
`requirements.txt`, `backend/**`) or the container's internal port
(8000) without making the matching change in the R2RA repo
(`buildspec.yml`, `deploy/docker-compose.eb.yml`) in the same sitting.

## Working agreements (mirrors R2RA)

- Commit and push after each unit of work.
- No PR unless explicitly asked.
- No secrets in the repo — runtime env vars live on the `r2ra-prod` EB
  environment.
- Cost posture: infra decisions for both projects are documented in
  R2RA's `docs/COST.md`; don't create new AWS resources for this repo
  without checking there first.
