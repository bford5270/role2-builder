# Role2 Builder

Role2 Builder is a [Next.js](https://nextjs.org) frontend (deployed on Vercel at
[www.role2builder.org](https://www.role2builder.org)) backed by a FastAPI service
(`backend/`) reachable at [https://api.role2builder.org](https://api.role2builder.org).

## Getting Started (frontend)

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Deployment Architecture

> **Updated 2026-07-25:** the backend no longer runs in its own AWS environment.
> The dedicated Elastic Beanstalk environment `role2-builder-prod` was terminated
> for cost consolidation.

### Backend (FastAPI)

The FastAPI backend now runs as a **second Docker Compose service on the R2RA
production instance** (Elastic Beanstalk environment `r2ra-prod`, AWS account
`885232248320`, `us-east-1`), listening on **port 8080** of that instance.

Public entry is unchanged: **https://api.role2builder.org** is a CloudFront
distribution whose origin now points to
`r2ra-prod.eba-yg3nk3rp.us-east-1.elasticbeanstalk.com:8080`.

### Frontend (Next.js)

The Next.js frontend on Vercel ([www.role2builder.org](https://www.role2builder.org))
is unaffected by this change.

### CI/CD: the pipeline publishes, it does not deploy

The `role2-builder` CodePipeline no longer deploys anything. Its final stage
**uploads the built bundle** (`Dockerfile`, `backend/`, `requirements.txt`) to:

```
s3://r2ra-artifacts-885232248320/role2-builder/latest.zip
```

The R2RA repo's build pulls that bundle into its own deploy artifact — see
R2RA's `buildspec.yml` and `deploy/docker-compose.eb.yml`.

### Shipping a backend change (two-step deploy)

Shipping a backend change is now two steps:

1. Run the `role2-builder` pipeline (publishes the bundle to S3).
2. Run the `r2ra` pipeline (pulls the bundle and deploys to `r2ra-prod`).

Both pipelines currently need **manual starts** because GitHub push triggers are
broken pending a GitHub App connection fix:

```bash
aws codepipeline start-pipeline-execution --name role2-builder
aws codepipeline start-pipeline-execution --name r2ra
```

## Dockerfile / build bundle

The `Dockerfile` builds the FastAPI backend image consumed by the R2RA deploy.
The `buildspec.yml` artifact selection (`Dockerfile`, `backend/`,
`requirements.txt`) defines the exact bundle shape the R2RA deploy consumes.

> ⚠️ **Runtime contract — do not break these:**
>
> - The container must keep serving on **port 8000 internally** — the R2RA
>   compose file maps `8080 → 8000`.
> - The container receives only **`CORS_ORIGINS`** and **`GEMINI_API_KEY`** as
>   environment variables. They are set on the `r2ra-prod` EB environment, not
>   in this repo.
> - The container must **not assume a `DATABASE_URL`**.
> - Keep `Dockerfile`, `requirements.txt`, and the buildspec's artifact
>   selection (`Dockerfile`, `backend/`, `requirements.txt`) intact — the R2RA
>   deploy consumes exactly that bundle shape.

## Rollback path

If the co-hosted setup needs to be rolled back (for reference — not an
automated process):

1. Recreate a single-instance Elastic Beanstalk environment from the retained
   `role2-builder` application versions.
2. Point the `api.role2builder.org` CloudFront origin back to that environment.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!
