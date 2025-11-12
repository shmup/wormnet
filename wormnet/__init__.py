"""wormnet - minimal worms armageddon server"""

__version__ = "0.1.0"

from . import state, config, http, irc

__all__ = ["state", "config", "http", "irc"]
