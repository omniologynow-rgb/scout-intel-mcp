FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python deps
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

# Copy config
COPY .env.example .env

EXPOSE 8001

# Run the MCP server with SSE transport via uvicorn
CMD ["python", "-c", "from scout_mcp.mcp_server import mcp; mcp.run(transport='sse', port=8001)"]
