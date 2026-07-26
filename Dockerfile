# Deployed as a compose service inside the R2RA EB bundle (see README
# "Deployment Architecture"). Contract: must keep serving on port 8000,
# and the buildspec artifact must stay exactly Dockerfile + backend/ +
# requirements.txt — R2RA's build consumes that shape from
# s3://r2ra-artifacts-885232248320/role2-builder/latest.zip.
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/

EXPOSE 8000

CMD ["python", "-c", "import os,uvicorn; uvicorn.run('backend.main:app', host='0.0.0.0', port=int(os.environ.get('PORT',8000)), timeout_keep_alive=180)"]
