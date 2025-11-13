#!/usr/bin/env python3
"""HostingBuddy - IRC bot for creating Worms Armageddon game lobbies"""

import re
import socket
import requests


def send_line(sock, line):
    """Send a line to IRC socket with proper CRLF termination"""
    sock.sendall(f'{line}\r\n'.encode('utf-8'))


def connect_irc(host='localhost', port=6667):
    """Connect to IRC server and authenticate"""
    sock = socket.socket()
    sock.connect((host, port))
    send_line(sock, 'PASS ELSILRACLIHP')
    send_line(sock, 'NICK HostingBuddy')
    send_line(sock, 'USER hostingbuddy host server :Game hosting bot')
    return sock


def parse_privmsg(line):
    """Parse IRC PRIVMSG line to extract command info

    Returns dict with nick, ip, target, command, args if line contains !command
    Returns None otherwise
    """
    # Pattern: :nick!user@ip PRIVMSG target :!command args
    match = re.match(
        r':([^!]+)!([^@]+)@([^ ]+) PRIVMSG ([^ ]+) :!(\w+)(.*)',
        line
    )
    if not match:
        return None

    nick, user, ip, target, command, args = match.groups()
    return {
        'nick': nick,
        'ip': ip,
        'target': target,
        'command': command,
        'args': args
    }


def is_ping(line):
    """Check if line is a PING message"""
    return line.startswith('PING ')


def handle_ping(sock, line):
    """Respond to PING with PONG"""
    # Extract server from "PING :server"
    send_line(sock, line.replace('PING', 'PONG'))


class GameState:
    """Track active games created by users"""

    def __init__(self):
        self.games = {}

    def store_game(self, nick, game_id, channel):
        """Store game info for a user"""
        self.games[nick] = {
            'game_id': game_id,
            'channel': channel
        }

    def get_game(self, nick):
        """Get game info for a user, or None"""
        return self.games.get(nick)

    def has_game(self, nick):
        """Check if user has an active game"""
        return nick in self.games

    def remove_game(self, nick):
        """Remove user's game from tracking"""
        self.games.pop(nick, None)


def create_game(nick, ip, channel, scheme='Intermediate', http_base='http://localhost'):
    """Create game via HTTP API

    Returns game_id on success, None on failure
    """
    url = f'{http_base}/wormageddonweb/Game.asp'
    params = {
        'Cmd': 'Create',
        'Name': f"{nick}'s game",
        'Nick': nick,
        'HostIP': f'{ip}:17011',
        'Chan': channel,
        'Loc': 'US',
        'Type': '0',
        'Scheme': scheme
    }

    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200 and 'SetGameId:' in response.text:
            game_id = int(response.text.split(':')[1].strip())
            return game_id
    except Exception:
        pass

    return None


def close_game(game_id, http_base='http://localhost'):
    """Close game via HTTP API

    Returns True on success, False on failure
    """
    url = f'{http_base}/wormageddonweb/Game.asp'
    params = {
        'Cmd': 'Close',
        'GameID': game_id
    }

    try:
        response = requests.get(url, params=params, timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def handle_host_command(sock, msg, state, channel='#hell'):
    """Handle !host command to create a game"""
    nick = msg['nick']

    # Check if user already has a game
    if state.has_game(nick):
        send_line(sock, f"PRIVMSG {msg['target']} :{nick}: Close your existing game first")
        return

    # Create game
    game_id = create_game(nick, msg['ip'], channel)

    if game_id:
        state.store_game(nick, game_id, channel)
        send_line(sock, f"PRIVMSG {msg['target']} :{nick}: Game created! Use !close to remove it.")
    else:
        send_line(sock, f"PRIVMSG {msg['target']} :{nick}: Failed to create game, try again")


def handle_close_command(sock, msg, state):
    """Handle !close command to close a game"""
    nick = msg['nick']

    game = state.get_game(nick)
    if not game:
        send_line(sock, f"PRIVMSG {msg['target']} :{nick}: You don't have an active game")
        return

    success = close_game(game['game_id'])

    if success:
        state.remove_game(nick)
        send_line(sock, f"PRIVMSG {msg['target']} :{nick}: Game closed.")
    else:
        send_line(sock, f"PRIVMSG {msg['target']} :{nick}: Failed to close game")


def run_bot(host='localhost', port=6667, channels=None):
    """Main bot loop"""
    if channels is None:
        channels = ['#hell']

    print(f"Connecting to {host}:{port}...")
    sock = connect_irc(host, port)

    # Join channels
    for channel in channels:
        send_line(sock, f'JOIN {channel}')
        print(f"Joined {channel}")

    state = GameState()
    buffer = ''

    print("HostingBuddy ready!")

    try:
        while True:
            data = sock.recv(4096).decode('utf-8', errors='ignore')
            if not data:
                print("Connection closed")
                break

            buffer += data
            lines = buffer.split('\r\n')
            buffer = lines[-1]  # Keep incomplete line in buffer

            for line in lines[:-1]:
                if not line:
                    continue

                print(f"< {line}")

                # Handle PING
                if is_ping(line):
                    handle_ping(sock, line)
                    continue

                # Handle commands
                msg = parse_privmsg(line)
                if msg:
                    if msg['command'] == 'host':
                        # Extract channel from target or default
                        channel = msg['target'].lstrip('#') if msg['target'].startswith('#') else 'hell'
                        handle_host_command(sock, msg, state, channel)
                    elif msg['command'] == 'close':
                        handle_close_command(sock, msg, state)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        sock.close()


if __name__ == '__main__':
    run_bot()
