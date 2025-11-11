FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim

WORKDIR /app

COPY wormnet .
COPY wormnet.toml .
COPY wwwroot ./wwwroot

RUN chmod +x wormnet

EXPOSE 6667 80

CMD ["./wormnet"]
