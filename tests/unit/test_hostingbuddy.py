from unittest.mock import Mock, patch
import hostingbuddy


def test_send_line():
    """Test that send_line formats and sends IRC messages correctly"""
    mock_sock = Mock()
    hostingbuddy.send_line(mock_sock, "NICK HostingBuddy")
    mock_sock.sendall.assert_called_once_with(b"NICK HostingBuddy\r\n")


@patch("socket.socket")
def test_connect_irc(mock_socket_class):
    """Test IRC connection sequence"""
    mock_sock = Mock()
    mock_socket_class.return_value = mock_sock

    sock = hostingbuddy.connect_irc(host="localhost", port=6667)

    mock_sock.connect.assert_called_once_with(("localhost", 6667))
    assert mock_sock.sendall.call_count >= 3  # PASS, NICK, USER
    assert sock == mock_sock


def test_parse_privmsg():
    """Test parsing PRIVMSG to extract nick, IP, target, command"""
    line = ":TestPlayer!user@1.2.3.4 PRIVMSG HostingBuddy :!host"
    result = hostingbuddy.parse_privmsg(line)

    assert result is not None
    assert result["nick"] == "TestPlayer"
    assert result["ip"] == "1.2.3.4"
    assert result["target"] == "HostingBuddy"
    assert result["command"] == "host"
    assert result["args"] == ""


def test_parse_privmsg_with_args():
    """Test parsing PRIVMSG with arguments"""
    line = ":Player!user@5.6.7.8 PRIVMSG #AnythingGoes :!close now"
    result = hostingbuddy.parse_privmsg(line)

    assert result["nick"] == "Player"
    assert result["ip"] == "5.6.7.8"
    assert result["target"] == "#AnythingGoes"
    assert result["command"] == "close"
    assert result["args"] == " now"


def test_parse_privmsg_no_command():
    """Test parsing regular PRIVMSG without bot command"""
    line = ":Player!user@1.2.3.4 PRIVMSG #AnythingGoes :hello there"
    result = hostingbuddy.parse_privmsg(line)

    assert result is None


def test_handle_ping():
    """Test PING response with PONG"""
    mock_sock = Mock()
    hostingbuddy.handle_ping(mock_sock, "PING :server123")
    mock_sock.sendall.assert_called_once_with(b"PONG :server123\r\n")


def test_is_ping():
    """Test PING line detection"""
    assert hostingbuddy.is_ping("PING :server") is True
    assert hostingbuddy.is_ping("PING :wormnet.example.com") is True
    assert hostingbuddy.is_ping(":user PRIVMSG #chan :hi") is False
    assert hostingbuddy.is_ping("") is False


def test_game_state_store():
    """Test storing user game info"""
    state = hostingbuddy.GameState()
    state.store_game("PlayerName", 123, "#AnythingGoes")

    assert state.has_game("PlayerName") is True
    game = state.get_game("PlayerName")
    assert game["game_id"] == 123
    assert game["channel"] == "#AnythingGoes"


def test_game_state_remove():
    """Test removing user game"""
    state = hostingbuddy.GameState()
    state.store_game("PlayerName", 123, "#AnythingGoes")
    state.remove_game("PlayerName")

    assert state.has_game("PlayerName") is False
    assert state.get_game("PlayerName") is None


def test_game_state_nonexistent():
    """Test querying nonexistent game"""
    state = hostingbuddy.GameState()
    assert state.has_game("NoOne") is False
    assert state.get_game("NoOne") is None


@patch("requests.get")
def test_create_game_success(mock_get):
    """Test creating game via HTTP API"""
    mock_response = Mock()
    mock_response.text = "SetGameId: 123\n"
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    game_id = hostingbuddy.create_game(
        nick="TestPlayer", ip="1.2.3.4", channel="AnythingGoes"
    )

    assert game_id == 123
    mock_get.assert_called_once()
    call_args = mock_get.call_args
    assert call_args[1]["params"]["Cmd"] == "Create"
    assert call_args[1]["params"]["Nick"] == "TestPlayer"
    assert call_args[1]["params"]["HostIP"] == "1.2.3.4:17011"
    assert call_args[1]["params"]["Chan"] == "AnythingGoes"
    assert call_args[1]["params"]["Scheme"] == "Intermediate"


@patch("requests.get")
def test_create_game_failure(mock_get):
    """Test game creation failure"""
    mock_response = Mock()
    mock_response.text = "Error: something failed"
    mock_response.status_code = 500
    mock_get.return_value = mock_response

    game_id = hostingbuddy.create_game(
        nick="TestPlayer", ip="1.2.3.4", channel="AnythingGoes"
    )

    assert game_id is None


@patch("requests.get")
def test_close_game_success(mock_get):
    """Test closing game via HTTP API"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    result = hostingbuddy.close_game(game_id=123)

    assert result is True
    mock_get.assert_called_once()
    call_args = mock_get.call_args
    assert call_args[1]["params"]["Cmd"] == "Close"
    assert call_args[1]["params"]["GameID"] == 123


@patch("requests.get")
def test_close_game_failure(mock_get):
    """Test game close failure"""
    mock_get.side_effect = Exception("Network error")

    result = hostingbuddy.close_game(game_id=123)

    assert result is False


@patch("hostingbuddy.create_game")
def test_handle_host_command_success(mock_create):
    """Test handling !host command"""
    mock_create.return_value = 456
    mock_sock = Mock()
    state = hostingbuddy.GameState()

    msg = {
        "nick": "Player1",
        "ip": "10.0.0.1",
        "target": "HostingBuddy",
        "command": "host",
        "args": "",
    }

    hostingbuddy.handle_host_command(mock_sock, msg, state, channel="#AnythingGoes")

    assert state.has_game("Player1") is True
    assert state.get_game("Player1")["game_id"] == 456
    mock_sock.sendall.assert_called()
    call_text = mock_sock.sendall.call_args[0][0].decode()
    assert "Game created" in call_text


@patch("hostingbuddy.create_game")
def test_handle_host_command_already_has_game(mock_create):
    """Test !host when user already has a game"""
    mock_sock = Mock()
    state = hostingbuddy.GameState()
    state.store_game("Player1", 100, "#AnythingGoes")

    msg = {
        "nick": "Player1",
        "ip": "10.0.0.1",
        "target": "HostingBuddy",
        "command": "host",
        "args": "",
    }

    hostingbuddy.handle_host_command(mock_sock, msg, state, channel="#AnythingGoes")

    mock_create.assert_not_called()
    call_text = mock_sock.sendall.call_args[0][0].decode()
    assert "existing game" in call_text.lower()


@patch("hostingbuddy.create_game")
def test_handle_host_command_creation_fails(mock_create):
    """Test !host when API fails"""
    mock_create.return_value = None
    mock_sock = Mock()
    state = hostingbuddy.GameState()

    msg = {
        "nick": "Player1",
        "ip": "10.0.0.1",
        "target": "HostingBuddy",
        "command": "host",
        "args": "",
    }

    hostingbuddy.handle_host_command(mock_sock, msg, state, channel="#AnythingGoes")

    assert state.has_game("Player1") is False
    call_text = mock_sock.sendall.call_args[0][0].decode()
    assert "Failed" in call_text or "failed" in call_text


@patch("hostingbuddy.close_game")
def test_handle_close_command_success(mock_close):
    """Test handling !close command"""
    mock_close.return_value = True
    mock_sock = Mock()
    state = hostingbuddy.GameState()
    state.store_game("Player1", 789, "#AnythingGoes")

    msg = {
        "nick": "Player1",
        "ip": "10.0.0.1",
        "target": "HostingBuddy",
        "command": "close",
        "args": "",
    }

    hostingbuddy.handle_close_command(mock_sock, msg, state)

    assert state.has_game("Player1") is False
    mock_close.assert_called_once_with(789)
    call_text = mock_sock.sendall.call_args[0][0].decode()
    assert "closed" in call_text.lower()


@patch("hostingbuddy.close_game")
def test_handle_close_command_no_game(mock_close):
    """Test !close when user has no game"""
    mock_sock = Mock()
    state = hostingbuddy.GameState()

    msg = {
        "nick": "Player1",
        "ip": "10.0.0.1",
        "target": "HostingBuddy",
        "command": "close",
        "args": "",
    }

    hostingbuddy.handle_close_command(mock_sock, msg, state)

    mock_close.assert_not_called()
    call_text = mock_sock.sendall.call_args[0][0].decode()
    assert "don't have" in call_text.lower() or "no" in call_text.lower()
