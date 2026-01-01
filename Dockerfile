FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim

ENV TZ=Asia/Shanghai
ENV DEBIAN_FRONTEND=noninteractive
RUN apt update && apt install git -y && rm -rf /var/lib/apt/lists/*

WORKDIR /sleepy-project
RUN git clone --depth 1 https://github.com/sleepy-project/sleepy.git sleepy

WORKDIR /sleepy-project/sleepy
ENV UV_LINK_MODE=copy
RUN uv sync --locked --no-dev

EXPOSE 9010

RUN chmod 777 /sleepy-project/sleepy/
ENTRYPOINT []
CMD [".venv/bin/python", "main.py"]