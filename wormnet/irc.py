"""irc server for wormnet"""

import socket
import threading
import re
import logging
from pathlib import Path
from . import state, config


class IRCClient:
    """handles individual irc client connection"""

    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.nickname = None
        self.username = None
        self.realname = None  # stores "flags rank country version"
        self.registered = False
        self.password = None
        self.channels = set()

    def send(self, msg):
        """send message to client"""
        try:
            logging.debug(f"IRC {self.addr[0]}:{self.addr[1]} <- {msg}")
            self.sock.sendall(f"{msg}\r\n".encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError):
            pass

    def handle(self):
        """handle client connection"""
        buf = ""
        try:
            while True:
                data = self.sock.recv(4096).decode("utf-8", errors="ignore")
                if not data:
                    break

                buf += data
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.rstrip("\r")
                    if line:
                        self.process_line(line)
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
        finally:
            self.cleanup()

    def process_line(self, line):
        """process irc command"""
        logging.debug(f"IRC {self.addr[0]}:{self.addr[1]}: {line}")
        parts = line.split(" ")
        cmd = parts[0].upper()

        if cmd == "PASS":
            self.password = parts[1] if len(parts) > 1 else None

        elif cmd == "NICK":
            if len(parts) > 1:
                nick = parts[1]
                # validate nickname
                if re.match(r"^[a-zA-Z][a-zA-Z0-9\-`|\[\]{}\_^]{0,14}$", nick):
                    self.nickname = nick
                    self.check_registration()

        elif cmd == "USER":
            if len(parts) >= 4:
                self.username = parts[1]
                # extract realname (everything after the colon)
                # format: USER username hostname servername :flags rank country version
                if ":" in line:
                    self.realname = line.split(":", 1)[1]
                self.check_registration()

        elif cmd == "PING":
            self.send(f"PONG {config.IRC_HOST}")

        elif cmd == "JOIN" and self.registered:
            if len(parts) > 1:
                for channame in parts[1].split(","):
                    if channame.startswith("#") and channame in state.irc_channels:
                        # check if already in channel
                        if channame in self.channels:
                            continue
                        self.channels.add(channame)
                        with state.irc_lock:
                            state.irc_channels[channame]["users"].add(self.nickname)
                        # notify everyone in channel (including self)
                        # format: :nick!user@host JOIN :#channel
                        user_mask = f"{self.nickname}!~{self.username}@{self.addr[0]}"
                        join_msg = f":{user_mask} JOIN :{channame}"
                        self.send(join_msg)
                        self.broadcast_to_channel(channame, join_msg)
                        self.send(
                            f":{config.IRC_HOST} 332 {self.nickname} {channame} :{state.irc_channels[channame]['topic']}"
                        )
                        self.send_names(channame)

        elif cmd == "PART" and self.registered:
            if len(parts) > 1:
                channame = parts[1]
                if channame in self.channels:
                    # notify everyone before removing from channel
                    part_msg = f":{self.nickname} PART {channame}"
                    self.send(part_msg)
                    self.broadcast_to_channel(channame, part_msg)
                    self.channels.remove(channame)
                    with state.irc_lock:
                        state.irc_channels[channame]["users"].discard(self.nickname)

        elif cmd == "PRIVMSG" and self.registered:
            if len(parts) >= 3:
                target = parts[1]
                msg = " ".join(parts[2:])[1:]  # remove leading :
                if target.startswith("#") and target in self.channels:
                    self.broadcast_to_channel(
                        target, f":{self.nickname} PRIVMSG {target} :{msg}"
                    )

        elif cmd == "LIST" and self.registered:
            self.send(f":{config.IRC_HOST} 321 {self.nickname} Channel :Users Name")
            for channame, chandata in state.irc_channels.items():
                usercount = len(chandata["users"])
                self.send(
                    f":{config.IRC_HOST} 322 {self.nickname} {channame} {usercount} :{chandata['topic']}"
                )
            self.send(f":{config.IRC_HOST} 323 {self.nickname} :End of /LIST")

        elif cmd == "NAMES" and self.registered:
            if len(parts) > 1:
                self.send_names(parts[1])

        elif cmd == "WHO" and self.registered:
            # WHO [channel]
            target = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "*"
            with state.irc_lock:
                if target.startswith("#") and target in state.irc_channels:
                    # list users in specific channel - need to find client objects
                    for client in state.irc_clients:
                        if client.nickname in state.irc_channels[target]["users"]:
                            realname = (
                                client.realname if client.realname else client.nickname
                            )
                            username = client.username if client.username else "user"
                            self.send(
                                f":{config.IRC_HOST} 352 {self.nickname} {target} ~{username} {client.addr[0]} {config.IRC_HOST} {client.nickname} H :0 {realname}"
                            )
                else:
                    # list all users, showing which channel they're in
                    for client in state.irc_clients:
                        if client.nickname:
                            realname = (
                                client.realname if client.realname else client.nickname
                            )
                            username = client.username if client.username else "user"
                            # show first channel user is in, or * if none
                            channel = (
                                next(iter(client.channels)) if client.channels else "*"
                            )
                            self.send(
                                f":{config.IRC_HOST} 352 {self.nickname} {channel} ~{username} {client.addr[0]} {config.IRC_HOST} {client.nickname} H :0 {realname}"
                            )
                    target = "*"  # normalize for reply
            self.send(
                f":{config.IRC_HOST} 315 {self.nickname} {target} :End of /WHO list"
            )

        elif cmd == "MODE" and self.registered:
            if len(parts) > 1:
                # minimal mode support
                self.send(f":{config.IRC_HOST} 324 {self.nickname} {parts[1]} +")

        elif cmd == "MOTD" and self.registered:
            self.send_motd()

        elif cmd == "QUIT":
            self.cleanup()

    def check_registration(self):
        """check if client can be registered"""
        if self.nickname and self.username and not self.registered:
            if self.password != config.PASSWORD:
                self.send(f":{config.IRC_HOST} 464 * :Password incorrect")
                self.sock.close()
                return

            self.registered = True
            with state.irc_lock:
                state.irc_clients.append(self)

            # send welcome messages
            self.send(
                f":{config.IRC_HOST} 001 {self.nickname} :Welcome {self.nickname}"
            )
            self.send(
                f":{config.IRC_HOST} 002 {self.nickname} :Your host is {config.IRC_HOST}"
            )
            self.send(
                f":{config.IRC_HOST} 003 {self.nickname} :This server was created today"
            )
            self.send(
                f":{config.IRC_HOST} 004 {self.nickname} {config.IRC_HOST} WormNET 0 0 0"
            )
            self.send(
                f":{config.IRC_HOST} 005 {self.nickname} CHANTYPES=# :are supported by this server"
            )

            self.send_motd()

    def send_motd(self):
        """send message of the day"""
        self.send(
            f":{config.IRC_HOST} 375 {self.nickname} :- {config.IRC_HOST} Message of the Day -"
        )

        lines = []
        if config.MOTD_FILE and Path(config.MOTD_FILE).exists():
            try:
                lines = Path(config.MOTD_FILE).read_text().splitlines()
            except IOError:
                lines = ["Welcome to WormNET"]
        else:
            lines = ["Welcome to WormNET", "Have fun playing Worms Armageddon!"]

        for line in lines:
            self.send(f":{config.IRC_HOST} 372 {self.nickname} :- {line}")

        self.send(f":{config.IRC_HOST} 376 {self.nickname} :End of /MOTD command.")

    def send_names(self, channame):
        """send names list for channel"""
        if channame in state.irc_channels:
            users = " ".join(state.irc_channels[channame]["users"])
            self.send(f":{config.IRC_HOST} 353 {self.nickname} = {channame} :{users}")
            self.send(
                f":{config.IRC_HOST} 366 {self.nickname} {channame} :End of /NAMES list"
            )

    def broadcast_to_channel(self, channame, msg):
        """broadcast message to channel"""
        with state.irc_lock:
            for client in state.irc_clients:
                if client != self and channame in client.channels:
                    client.send(msg)

    def cleanup(self):
        """cleanup on disconnect"""
        # notify all channels user was in
        if self.nickname:
            quit_msg = f":{self.nickname} QUIT :Client disconnected"
            for channame in self.channels:
                self.broadcast_to_channel(channame, quit_msg)
            logging.info(f"IRC: {self.addr[0]}:{self.addr[1]} disconnecting: Quit")
        else:
            logging.info(
                f"IRC: {self.addr[0]}:{self.addr[1]} disconnected before registering"
            )

        with state.irc_lock:
            if self in state.irc_clients:
                state.irc_clients.remove(self)
            for channame in self.channels:
                if channame in state.irc_channels:
                    state.irc_channels[channame]["users"].discard(self.nickname)
        try:
            self.sock.close()
        except OSError:
            pass


def run_server():
    """run irc server"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", config.IRC_PORT))
    sock.listen(5)
    logging.info(f"IRC server listening on port {config.IRC_PORT}")

    while True:
        try:
            client_sock, addr = sock.accept()
            logging.info(f"New IRC connection from {addr[0]}:{addr[1]}")
            client = IRCClient(client_sock, addr)
            thread = threading.Thread(target=client.handle, daemon=True)
            thread.start()
        except OSError:
            pass
