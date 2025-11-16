#!/usr/bin/env python3
"""HostingBuddy - IRC bot for creating Worms Armageddon game lobbies"""

import argparse
import logging
import re
import socket
import requests

# Global logger instance
logger = logging.getLogger('hostingbuddy')


def setup_logging(level_name):
    """Configure logging with the specified level

    Args:
        level_name: Logging level name (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Configured logger instance
    """
    # Map level name to logging constant, default to INFO for invalid levels
    level = getattr(logging, level_name.upper(), logging.INFO)

    # Configure the logger
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates in tests
    logger.handlers.clear()

    # Create console handler with formatting
    handler = logging.StreamHandler()
    handler.setLevel(level)

    # Format: timestamp - level - message
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger


def create_argument_parser():
    """Create and configure argument parser

    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(description='HostingBuddy - IRC bot for creating Worms Armageddon game lobbies',
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="""
Examples:
  %(prog)s
  %(prog)s --host wormnet.example.com --port 6668
  %(prog)s --channels '#test' '#hell' --log-level DEBUG
  %(prog)s -c config.ini -l WARNING
        """)

    parser.add_argument('--host', default='localhost', help='IRC server hostname (default: localhost)')

    parser.add_argument('--port', type=int, default=6667, help='IRC server port (default: 6667)')

    parser.add_argument('--channels', nargs='+', default=['#hell'], help='IRC channels to join (default: #hell)')

    parser.add_argument('-c', '--config', help='Path to configuration file (optional)')

    parser.add_argument('-l',
                        '--log-level',
                        default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Logging level (default: INFO)')

    return parser


def send_line(sock, line):
    """Send a line to IRC socket with proper CRLF termination"""
    sock.sendall(f'{line}\r\n'.encode('utf-8'))


def connect_irc(host='localhost', port=6667):
    """Connect to IRC server and authenticate"""
    sock = socket.socket()
    sock.connect((host, port))
    send_line(sock, 'PASS ELSILRACLIHP')
    send_line(sock, 'NICK HostingBuddy')
    # USER <username>   <hostname> <servername> :<flags> <rank> <country> <version>
    # USER HostingBuddy host       server       :48      0      US        3.8.1
    send_line(sock, 'USER HostingBuddy host server :51 11 ZZ 3.8.1')
    return sock


def parse_privmsg(line):
    """Parse IRC PRIVMSG line to extract command info

    Returns dict with nick, ip, target, command, args if line contains command
    Returns None otherwise
    """
    # Pattern: :nick!user@ip PRIVMSG target :!?command args (! is optional)
    match = re.match(r':([^!]+)!([^@]+)@([^ ]+) PRIVMSG ([^ ]+) :!?(\w+)(.*)', line)
    if not match:
        return None

    nick, user, ip, target, command, args = match.groups()
    return {'nick': nick, 'ip': ip, 'target': target, 'command': command, 'args': args}


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
        self.games[nick] = {'game_id': game_id, 'channel': channel}

    def get_game(self, nick):
        """Get game info for a user, or None"""
        return self.games.get(nick)

    def has_game(self, nick):
        """Check if user has an active game"""
        return nick in self.games

    def remove_game(self, nick):
        """Remove user's game from tracking"""
        self.games.pop(nick, None)


def create_game(nick, ip, channel, scheme='Intermediate', http_base='http://localhost:8081'):
    """Create game via HTTP API

    Returns game_id on success, None on failure
    """
    url = f'{http_base}/wormageddonweb/Game.asp'
    params = {
        'Cmd': 'Create',
        'Name': f"{scheme}.for.{nick}",
        'Nick': nick,
        'HostIP': f'{ip}:17011',
        'Pwd': '',  # No password
        'Chan': channel,
        'Loc': '48',  # User flags - 48 is standard for most clients
        'Type': '0',
        'Scheme': scheme
    }

    try:
        logger.debug(f"Creating game: {url}?{params}")
        response = requests.get(url, params=params, timeout=5)
        logger.debug(f"Response status: {response.status_code}")
        logger.debug(f"Response text: {response.text!r}")
        logger.debug(f"Response headers: {dict(response.headers)}")
        if response.status_code == 200 and 'SetGameId' in response.headers:
            # Header format is "SetGameId: : 123" (note the ": " prefix)
            game_id_header = response.headers.get('SetGameId')
            game_id = int(game_id_header.split(':')[1].strip())
            return game_id
    except Exception as e:
        logger.error(f"Exception creating game: {e}")
        pass

    return None


def close_game(game_id, http_base='http://localhost:8081'):
    """Close game via HTTP API

    Returns True on success, False on failure
    """
    url = f'{http_base}/wormageddonweb/Game.asp'
    params = {'Cmd': 'Close', 'GameID': game_id}

    try:
        response = requests.get(url, params=params, timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def handle_host_command(sock, msg, state, channel='#hell'):
    """Handle !host command to create a game"""
    nick = msg['nick']
    # Reply to channel if command was in channel, otherwise PM the user
    reply_to = msg['target'] if msg['target'].startswith('#') else msg['nick']

    # Check if user already has a game
    if state.has_game(nick):
        send_line(sock, f"PRIVMSG {reply_to} :{nick}: Close your existing game first")
        return

    # Create game
    game_id = create_game(nick, msg['ip'], channel)

    if game_id:
        state.store_game(nick, game_id, channel)
        send_line(
            sock,
            f"PRIVMSG {reply_to} :{nick}: Game created (ID: {game_id}, IP: {msg['ip']}:17011). Use !close to remove it."
        )
    else:
        send_line(sock, f"PRIVMSG {reply_to} :{nick}: Failed to create game, try again")


def handle_close_command(sock, msg, state):
    """Handle !close command to close a game"""
    nick = msg['nick']
    # Reply to channel if command was in channel, otherwise PM the user
    reply_to = msg['target'] if msg['target'].startswith('#') else msg['nick']

    game = state.get_game(nick)
    if not game:
        send_line(sock, f"PRIVMSG {reply_to} :{nick}: You don't have an active game")
        return

    success = close_game(game['game_id'])

    if success:
        state.remove_game(nick)
        send_line(sock, f"PRIVMSG {reply_to} :{nick}: Game closed.")
    else:
        send_line(sock, f"PRIVMSG {reply_to} :{nick}: Failed to close game")


def run_bot(host='localhost', port=6667, channels=None):
    """Main bot loop"""
    if channels is None:
        channels = ['#hell']

    logger.info(f"Connecting to {host}:{port}...")
    sock = connect_irc(host, port)

    # Join channels
    for channel in channels:
        send_line(sock, f'JOIN {channel}')
        logger.info(f"Joined {channel}")

    state = GameState()
    buffer = ''

    logger.info("HostingBuddy ready!")

    try:
        while True:
            data = sock.recv(4096).decode('utf-8', errors='ignore')
            if not data:
                logger.info("Connection closed")
                break

            buffer += data
            lines = buffer.split('\r\n')
            buffer = lines[-1]  # Keep incomplete line in buffer

            for line in lines[:-1]:
                if not line:
                    continue

                logger.debug(f"< {line}")

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
        logger.info("Shutting down...")
    finally:
        sock.close()


def main():
    """Main entry point for HostingBuddy"""
    parser = create_argument_parser()
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)

    logger.info("Starting HostingBuddy")
    logger.debug(f"Arguments: host={args.host}, port={args.port}, channels={args.channels}")

    # Run the bot
    run_bot(host=args.host, port=args.port, channels=args.channels)


if __name__ == '__main__':
    main()
