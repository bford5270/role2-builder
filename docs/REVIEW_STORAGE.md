# Review storage (expert review + scenario library)

History, expert review/sign-off and the approved-case library need a database.
Everything else (generation, packages, live controller from `cases.json`) works
without one.

**Decision (2026-09-23):** a separate `role2builder` database, owned by its own
login role, on R2RA's existing Aurora Serverless v2 cluster `r2ra-aurora`
(us-east-1, account 885232248320). No new AWS resource; cost is the ACU time
the builder adds while in use. See R2RA `docs/COST.md` for the cluster's
cost posture (0–2 ACU, auto-pause after 300 s).

Tradeoffs accepted:
- Builder and R2RA share a database failure domain (separate DB + role limits
  blast radius, doesn't remove it).
- First request after ≥5 min idle waits ~15 s for the cluster to resume.
- The builder must never hold idle connections (it uses `NullPool`), or the
  cluster can't auto-pause and idle cost jumps to 24/7 ACU billing.

## One-time setup (run with AWS credentials for 885232248320)

### 0. R2RA passthrough (pending — needs a push to the R2RA repo)

Apply [`r2ra-compose-rb-database-url.patch`](r2ra-compose-rb-database-url.patch)
in the R2RA repo (`git apply`) and push to `main`. It adds one line to the
role2builder service in `deploy/docker-compose.eb.yml`:
`DATABASE_URL: ${RB_DATABASE_URL:-}`. It is safe to ship before steps 1–2:
while the property is unset, the value is empty and the builder runs without
storage.

### 1. Create the role and database

Using the RDS Data API (enabled on the cluster; master creds are in Secrets
Manager as `r2ra-aurora-master`). Generate a strong password first and keep it
out of shell history, e.g. `read -s RB_PW`.

```bash
CLUSTER_ARN=$(aws rds describe-db-clusters --db-cluster-identifier r2ra-aurora \
  --query 'DBClusters[0].DBClusterArn' --output text)
SECRET_ARN=$(aws secretsmanager describe-secret --secret-id r2ra-aurora-master \
  --query ARN --output text)
sql() { aws rds-data execute-statement --resource-arn "$CLUSTER_ARN" \
  --secret-arn "$SECRET_ARN" --database postgres --sql "$1"; }

sql "CREATE ROLE role2builder LOGIN PASSWORD '$RB_PW'"
sql "CREATE DATABASE role2builder OWNER role2builder"
```

`CREATE DATABASE` can't run inside a transaction; the Data API runs single
statements outside one, so the two calls above work as written. The first call
may fail with a resume timeout if the cluster was paused. Re-run it.

The builder creates its own tables on first start (`exercises`, `jobs`,
`case_reviews`, `review_comments`).

### 2. Give the builder its connection string

Add an EB environment property on `r2ra-prod` (Configuration → Updates,
monitoring, and logging → Environment properties):

```
RB_DATABASE_URL=postgresql://role2builder:<password>@<r2ra-aurora writer endpoint>:5432/role2builder?sslmode=require
```

Saving the property triggers an EB environment update (a brief blip for both
apps on the single instance). R2RA's `deploy/docker-compose.eb.yml` passes it
to the role2builder container as `DATABASE_URL` (the R2RA container never sees
it, and the builder never sees R2RA's `DATABASE_URL`). If the property is unset
the builder simply runs without storage.

No security-group change is needed: the builder runs on the same instance that
R2RA already uses to reach the cluster.

### 3. Verify

```bash
curl -s https://api.role2builder.org/reviews/status   # {"enabled":true}
```

Then generate a small exercise and open it from History → Expert review.

## Rollback

Remove `RB_DATABASE_URL` from the EB environment. The builder falls back to
no storage. The `role2builder` database can be dropped with
`DROP DATABASE role2builder; DROP ROLE role2builder;` once nothing needs it.
