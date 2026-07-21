# Poirot Dockerfile — 深度研究 Agent 容器镜像
#
# 构建: docker build -t poirot .
# 运行: docker run -it --rm poirot          (TUI 交互)
#        docker run --rm poirot run "问题"   (单次研究)
#
# 镜像包含: Python 3.12 + 项目代码 + 全部依赖 + Node.js（MCP stdio server 支持）
# 挂载卷: /app/.poirot（运行时数据） /app/skills（用户 skill）

FROM python:3.12-slim AS base

# 系统依赖：git（skill clone）+ curl + Node.js（MCP stdio server 如 freeweb-mcp）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制依赖描述（利用 Docker layer cache）
COPY pyproject.toml ./
COPY poirot/ poirot/

# 安装项目（editable + dev 测试工具）
# optional provider 包按需安装：pip install -e ".[anthropic,gemini,ollama]"
RUN pip install --no-cache-dir -e ".[dev]"

# 运行时数据卷（.poirot: DB/logs/artifacts，skills: 用户 skill）
VOLUME ["/app/.poirot", "/app/skills"]

# 默认环境变量（可被 -e 或 .env 覆盖）
ENV POIROT_SKILL_DB_PATH=/app/.poirot/skills.db \
    POIROT_MCP_CONFIG_PATH=/app/.poirot/mcp_servers.yaml \
    PYTHONUNBUFFERED=1

# 入口：poirot 命令
ENTRYPOINT ["poirot"]
CMD []
