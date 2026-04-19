FROM python:3.11-slim

WORKDIR /app

# Install ALL system deps for building Python C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    libxml2-dev libxslt1-dev \
    libffi-dev libssl-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip + install build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel hatchling

# Install dependencies first (binary wheels where available)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copy source and install package only (deps already installed)
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir --no-deps .

# MCPize injects env vars at runtime — no .env needed

# stdio transport (MCPize wraps with mcp-proxy for HTTP)
CMD ["scout-intel-mcp"]
