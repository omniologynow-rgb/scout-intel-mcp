FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

ENV MCP_TRANSPORT=streamable-http
ENV PORT=8080
EXPOSE 8080

CMD ["scout-intel-mcp"]
