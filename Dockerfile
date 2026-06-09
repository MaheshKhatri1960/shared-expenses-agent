# Dockerfile for Shared Expenses ADK Agent
# Based on official ADK Cloud Run deployment documentation
# Python 3.11 slim — stable, well-supported on Cloud Run

FROM python:3.11-slim

# ── System dependencies ───────────────────────────────────────────────────────
# Install Node.js 20 LTS for MongoDB MCP Server (runs via npx)
# Use official NodeSource setup script — most reliable method
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Verify installations ──────────────────────────────────────────────────────
RUN node --version && npx --version

# ── Pre-cache MongoDB MCP Server ─────────────────────────────────────────────
# Pre-download via npx so it is cached in the image
# This avoids cold start delays when the agent first uses MCP
# The || true allows build to continue even if help output exits non-zero
RUN npx -y mongodb-mcp-server@latest --help 2>/dev/null || true

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
# Copy requirements first — Docker layer caching means this only
# re-runs when requirements.txt changes, not on every code change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Agent code ────────────────────────────────────────────────────────────────
COPY . .

# ── Environment ───────────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# ── Port ──────────────────────────────────────────────────────────────────────
EXPOSE 8080

# ── Start command ─────────────────────────────────────────────────────────────
# Use adk api_server for production (not adk web which is dev-only)
# --host 0.0.0.0 required for Cloud Run to receive external traffic
# --port 8080 is Cloud Run default
# The dot "." tells ADK to look for agent in current directory
CMD ["adk", "api_server", "--host", "0.0.0.0", "--port", "8080", "."]
