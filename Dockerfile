FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

# Ensure setuptools available (needed by legacy deps)
RUN pip install --no-cache-dir "setuptools>=65"

# Copy and install Python deps
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

# MCPize injects env vars at runtime — no .env file needed

EXPOSE 8001

CMD ["python", "-m", "scout_mcp.mcp_server"]
