FROM python:3.12-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /sleepy

COPY . .

RUN ["uv", "sync"]

EXPOSE 9010

VOLUME ["/sleepy/data"]

CMD ["uv", "run", "main.py"]
