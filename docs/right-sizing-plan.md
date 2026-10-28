# Plan: bring `r2ra-prod` back down from t4g.small to t4g.micro

Written 2026-10-28. Owner: Brian. Cost posture: see CLAUDE.md and R2RA's cost doc.

## Why we went up

`r2ra-prod` (single EB instance, shared by R2RA and this backend) ran on a
`t4g.micro` (1 GB RAM, ~$6.13/mo). On 2026-10-28 three `r2ra` pipeline runs in a
row failed (00:09, 03:51 and 05:33 UTC). EB logged 14-minute instance command
timeouts for the last two (I did not inspect the first). The kernel log showed
the OOM killer repeatedly killing `python` in a container, and the last failure
took the API down (504s) until a reboot. On 2026-10-28 the instance type was changed to
`t4g.small` (2 GB, ~$12.26/mo) through the EB environment setting
`aws:ec2:instances / InstanceTypes`.

**Cost of the upgrade: about +$6.13/month (~$74/year).** Nothing else changed:
the Elastic IP is part of the EB stack and moved with the instance, so the Gemini
key's IP restriction stays valid.

## Working theory (verify before acting)

The pressure is probably at **deploy time**, not steady state: the EB bundle ships a
`Dockerfile`, so the instance itself may be building the image (pip installs of
pandas / matplotlib / google-genai) while the old containers keep running. That
needs far more memory than serving traffic. I have not confirmed this; R2RA's
`deploy/docker-compose.eb.yml` and `buildspec.yml` were not available locally.

## Steps, in order, each free unless noted

1. **Measure on the new instance** (needs permission to run read-only SSM commands):
   `free -m`, `docker stats --no-stream`, and `dmesg | grep -i oom` right after
   a deploy, and again an hour later. Record peak total memory used.
2. **Confirm or reject the build-on-instance theory.** Read R2RA's buildspec and
   compose file. If the instance builds images, move the build to CodeBuild and
   push to ECR; the instance then only pulls. ECR storage is about $0.10/GB-month
   (a few image layers: cents). This is the fix most likely to make micro viable.
3. **Trim memory in this backend:** import pandas and matplotlib lazily (only the
   document-export paths need them), keep uvicorn at one worker, and confirm no
   large objects are held in `_packages` / `_jobs` longer than needed.
4. **Add a swap file as a safety net** (1 GB, on the existing 8 GB disk, $0).
   Put it in an `.ebextensions` file in R2RA's repo so it survives instance
   replacement, rather than creating it by hand.

## When to go back to t4g.micro

Do it only when **all** of these hold:

- Steps 2-4 are done (or step 1 shows peak memory well under ~700 MB including
  deploys).
- At least 3 consecutive deploys succeeded on t4g.small with no OOM lines in the
  console log (`ec2 get-console-output`) and no EB "timed out" events.
- 30 days have passed since the upgrade (earliest: **2026-11-28**).

Do the downgrade as one EB change (`InstanceTypes = t4g.micro`). It replaces the
instance (a few minutes of API downtime; do it off-hours), then **deploy
immediately** to prove it works.

## Rollback

If the first deploy on micro fails or any OOM appears: set `InstanceTypes` back to
`t4g.small` the same way. No data is lost either way (saved exercises live in S3).

## Tracking the cost while on small

Check Cost Explorer filtered to EC2 for `r2ra-prod` at the end of November. Expect
roughly $12/month for the instance, versus about $6 before.
