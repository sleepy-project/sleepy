FROM python:3.12-slim-trixie

RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y nodejs \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

RUN corepack enable \
 && corepack prepare pnpm@latest --activate

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /sleepy

COPY pyproject.toml uv.lock ./
RUN ["uv", "sync"]

COPY . .

EXPOSE 9010
VOLUME ["/sleepy/data"]

CMD ["uv", "run", "main.py"]

