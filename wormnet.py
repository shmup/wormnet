#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["flask", "tomli"]
# ///
"""minimal wormnet server for worms armageddon"""
import argparse
import logging
import threading
from pathlib import Path
from wormnet import config, http, irc


def main():
    """entrypoint for wormnet server"""
    # parse CLI arguments
    parser = argparse.ArgumentParser(
        description="minimal wormnet server for worms armageddon"
    )
    parser.add_argument(
        "-c",
        "--config",
        default="wormnet.toml",
        help="path to config file (default: wormnet.toml)",
    )
    args = parser.parse_args()

    # load config if file exists, otherwise use defaults
    config_path = Path(args.config)
    if config_path.exists():
        config.load_config(config_path)
    else:
        # set up default logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        logging.info(f"Config file '{args.config}' not found, using defaults")
        logging.info(f"  HTTP port: {config.HTTP_PORT}")
        logging.info(f"  IRC port: {config.IRC_PORT}")
        logging.info(f"  IRC host: {config.IRC_HOST}")
        logging.info(f"  Channels: {', '.join(config.CHANNELS.keys())}")
        config.build_irc_channels()

    # start irc server in background
    irc_thread = threading.Thread(target=irc.run_server, daemon=True)
    irc_thread.start()

    # start http server
    logging.info(f"HTTP server starting on port {config.HTTP_PORT}")
    logging.info(f"Configure Worms to connect to: {config.IRC_HOST}")
    http.app.run(host="0.0.0.0", port=config.HTTP_PORT, threaded=True)


if __name__ == "__main__":
    main()
