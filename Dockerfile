FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libxml2-dev libxslt1-dev libffi-dev libssl-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools wheel

COPY pyproject.toml .
COPY src/ src/
RUN pip install .

CMD ["scout-intel-mcp"]
