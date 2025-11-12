"""shared state for wormnet server"""

import threading

# game storage
games = {}
game_counter = 0
games_lock = threading.Lock()

# irc state
irc_clients = []
irc_channels = {}
irc_lock = threading.Lock()
