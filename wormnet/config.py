"""configuration management for wormnet"""

import tomli
import logging
from . import state

# defaults
DEFAULT_HTTP_PORT = 80
DEFAULT_IRC_PORT = 6667
DEFAULT_IRC_HOST = ""  # empty = auto-detect
DEFAULT_CONNECT_PORT = None  # port to announce in <CONNECT> (None = use default 6667)
DEFAULT_PASSWORD = "ELSILRACLIHP"
DEFAULT_GAME_TIMEOUT = 300  # 5 minutes
DEFAULT_CHANNELS = {
    "AnythingGoes": {"topic": "Anything goes!", "icon": 0, "scheme": "Pf,Be"},
    "PartyTime": {"topic": "Party time!", "icon": 1, "scheme": "Pa,Ba"},
}

# runtime config
HTTP_PORT = DEFAULT_HTTP_PORT
IRC_PORT = DEFAULT_IRC_PORT
IRC_HOST = DEFAULT_IRC_HOST
CONNECT_PORT = DEFAULT_CONNECT_PORT
PASSWORD = DEFAULT_PASSWORD
GAME_TIMEOUT = DEFAULT_GAME_TIMEOUT
CHANNELS = DEFAULT_CHANNELS.copy()
MOTD_FILE = None
NEWS_FILE = None


def build_irc_channels():
    """build irc channels from config"""
    state.irc_channels = {
        f"#{name}": {"users": set(), "topic": f"{ch['icon']:02d} {ch['topic']}"}
        for name, ch in CHANNELS.items()
    }


def load_config(config_file):
    """load configuration from TOML file"""
    global HTTP_PORT, IRC_PORT, IRC_HOST, CONNECT_PORT, MOTD_FILE, NEWS_FILE, CHANNELS

    with open(config_file, "rb") as f:
        config = tomli.load(f)

    # configure logging
    log_level = config.get("logging", {}).get("level", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # load irc config
    IRC_PORT = config.get("irc", {}).get("port", IRC_PORT)
    IRC_HOST = config.get("irc", {}).get("ip", IRC_HOST)
    MOTD_FILE = config.get("irc", {}).get("motd_file")

    # load http config
    HTTP_PORT = config.get("http", {}).get("port", HTTP_PORT)
    CONNECT_PORT = config.get("http", {}).get("connect_port")
    NEWS_FILE = config.get("http", {}).get("news_file")

    # load channels
    if "channels" in config:
        CHANNELS = {name: cfg for name, cfg in config["channels"].items()}

    if not CHANNELS:
        CHANNELS = DEFAULT_CHANNELS.copy()

    build_irc_channels()

    logging.info(f"Loaded config from {config_file}")
    logging.info(f"  HTTP port: {HTTP_PORT}")
    logging.info(f"  IRC port: {IRC_PORT}")
    logging.info(f"  IRC host: {IRC_HOST}")
    logging.info(f"  Channels: {', '.join(CHANNELS.keys())}")
