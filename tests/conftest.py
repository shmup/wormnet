"""pytest fixtures for wormnet tests"""

import socket
import threading
import time
import pytest
from wormnet import config, state as state_module


@pytest.fixture(scope="function", autouse=True)
def reset_state():
    """Reset global state before each test"""
    state_module.irc_clients.clear()
    state_module.games.clear()


@pytest.fixture
def setup_test_config():
    """Setup test configuration"""
    # save original values
    orig_port = config.IRC_PORT
    orig_host = config.IRC_HOST
    orig_channels = config.CHANNELS.copy()
    orig_irc_channels = state_module.irc_channels.copy()

    # set test config
    config.IRC_HOST = "127.0.0.1"
    config.CHANNELS = {
        "heaven": {
            "scheme": "Pf,Be",
            "topic": "Test Heaven",
            "icon": 0,
        },
        "AnythingGoes": {
            "scheme": "In,Pr",
            "topic": "Anything goes!",
            "icon": 1,
        },
    }
    config.build_irc_channels()

    yield

    # restore original values
    config.IRC_PORT = orig_port
    config.IRC_HOST = orig_host
    config.CHANNELS = orig_channels
    state_module.irc_channels = orig_irc_channels


@pytest.fixture
def irc_server(setup_test_config):
    """Start IRC server on random port"""
    # create socket to get random port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.listen(5)

    # update config
    config.IRC_PORT = port

    # run server in thread
    def server_loop():
        while True:
            try:
                from wormnet.irc import IRCClient

                client_sock, addr = sock.accept()
                client = IRCClient(client_sock, addr)
                thread = threading.Thread(target=client.handle, daemon=True)
                thread.start()
            except OSError:
                break

    server_thread = threading.Thread(target=server_loop, daemon=True)
    server_thread.start()

    time.sleep(0.1)  # let server start

    yield "127.0.0.1", port

    sock.close()


class IRCTestClient:
    """Helper class for IRC protocol testing"""

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.responses = []

    def connect(self):
        """Connect to IRC server"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        self.sock.settimeout(2.0)

    def send(self, line):
        """Send IRC command"""
        self.sock.sendall(f"{line}\r\n".encode())

    def recv_line(self):
        """Receive one line"""
        buf = b""
        while b"\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        if b"\n" in buf:
            line, rest = buf.split(b"\n", 1)
            decoded = line.decode().strip()
            self.responses.append(decoded)
            return decoded
        return None

    def recv_until(self, end_marker, timeout=2.0):
        """Receive lines until marker is found"""
        lines = []
        self.sock.settimeout(timeout)
        try:
            while True:
                line = self.recv_line()
                if line is None:
                    break
                lines.append(line)
                if end_marker in line:
                    break
        except socket.timeout:
            pass
        return lines

    def close(self):
        """Close connection"""
        if self.sock:
            try:
                self.sock.close()
            except:
                pass


@pytest.fixture
def irc_client(irc_server):
    """Create IRC test client"""
    host, port = irc_server
    client = IRCTestClient(host, port)
    client.connect()
    yield client
    client.close()
