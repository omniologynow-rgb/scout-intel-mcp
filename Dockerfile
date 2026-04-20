FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir . && \
    python -c "from scout_mcp.mcp_server import mcp; print(f'[build] Scout MCP loaded: {len(list(mcp.list_tools.__wrapped__(mcp)))} tools' if hasattr(mcp.list_tools, '__wrapped__') else '[build] Scout MCP loaded OK')"

ENV MCP_TRANSPORT=streamable-http
ENV PORT=8080
EXPOSE 8080

CMD ["scout-intel-mcp"]
