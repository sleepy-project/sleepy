FROM node:22-slim AS frontend-builder

RUN corepack enable
WORKDIR /build/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.13-slim-trixie AS runtime

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /sleepy

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

COPY . .
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

EXPOSE 9010
VOLUME ["/sleepy/data"]

CMD ["uv", "run", "--no-sync", "main.py"]
