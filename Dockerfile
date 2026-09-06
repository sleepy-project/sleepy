FROM python:3.13-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /sleepy

COPY pyproject.toml uv.lock* ./
RUN ["uv", "sync", "--no-dev"]

COPY . .

EXPOSE 9010
VOLUME ["/sleepy/data"]

# 前端插件迁入 builtin/frontend 后, 这里需要重新加上 nodejs + pnpm 来构建前端资源
CMD ["uv", "run", "main.py"]
