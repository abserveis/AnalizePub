# ─────────────────────────────────────────────────────────────────────────────
# AnalizePub — Dockerfile
# Python 3.11 + Java (for EPUBCheck). PDF generation is delegated to the
# user's browser via window.print(), so we do not ship the WeasyPrint stack.
# Final image is intentionally slim: no node, no build chain at runtime.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    DEBIAN_FRONTEND=noninteractive

# ── System packages ─────────────────────────────────────────────────────────
# - default-jre-headless : EPUBCheck requires Java
# - libxml2 / libxslt    : lxml runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-jre-headless \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# ── App ─────────────────────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application source last so that requirements get cached aggressively.
COPY epub_a11y ./epub_a11y
COPY dashboard ./dashboard

# Create non-root runtime user.
RUN useradd --system --create-home --uid 1000 analizepub \
    && mkdir -p /tmp/analizepub_sessions \
    && chown -R analizepub:analizepub /app /tmp/analizepub_sessions

USER analizepub

EXPOSE 8080

# Single-process server — http.server is good enough for this workload.
CMD ["python", "-m", "dashboard.app"]
