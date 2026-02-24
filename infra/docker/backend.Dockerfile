###########
# Builder #
###########
FROM python:3.11-slim AS build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# 如有需要编译依赖（极少数情况下），保留 build-essential
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install --no-cache-dir uv

# 先拷贝依赖声明文件，最大化 Docker layer cache 命中
COPY pyproject.toml uv.lock ./

# 创建 venv 并严格按 lock 同步（--frozen：不允许改 lock）
RUN uv venv --python 3.11 \
 && uv sync --no-dev --frozen

###########
# Runtime #
###########
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV=prod \
    PYTHONPATH=/app \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# 拷贝虚拟环境（包含所有依赖）
COPY --from=build /app/.venv /app/.venv

# 拷贝代码
COPY apps/backend ./apps/backend
COPY core ./core
COPY agent ./agent
COPY config.toml ./config.toml

EXPOSE 8000
CMD ["uvicorn", "apps.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]