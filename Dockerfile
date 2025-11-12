FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim

WORKDIR /app

COPY wormnet.py .
COPY wormnet/ ./wormnet/
COPY wormnet.toml .
COPY wwwroot ./wwwroot

RUN chmod +x wormnet.py

EXPOSE 6667 80

CMD ["./wormnet.py"]
