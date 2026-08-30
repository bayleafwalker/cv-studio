# CV Studio as a small internal service: the same server.py, WeasyPrint for real PDFs,
# one folder per person under /data (CV_STUDIO_PERSONS=1). No database.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 libcairo2 libgdk-pixbuf-2.0-0 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "WeasyPrint>=68,<69"
WORKDIR /app
COPY server.py pyproject.toml ./
COPY static/ static/
COPY templates/ templates/
COPY content/cv.sample.json content/cv.sample.json
RUN mkdir -p /data && chown 65532:65532 /data
USER 65532:65532
ENV CV_STUDIO_CONTENT=/data CV_STUDIO_PERSONS=1 PYTHONUNBUFFERED=1 XDG_CACHE_HOME=/tmp
EXPOSE 8080
VOLUME ["/data"]
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8080"]
