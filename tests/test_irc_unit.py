"""
Fast unit tests for IRC protocol - uses mocks instead of real sockets

Tests the same what.txt protocol requirements as integration tests,
but runs in milliseconds instead of seconds.
"""

import pytest
import re
from unittest.mock import Mock, call
from wormnet.irc import IRCClient
from wormnet import state, config


@pytest.fixture
def mock_client():
    """Create IRCClient with mocked socket"""
    mock_sock = Mock()
    mock_sock.sendall = Mock()
    client = IRCClient(mock_sock, ("127.0.0.1", 12345))
    return client, mock_sock


def get_sent_messages(mock_sock):
    """Extract all messages sent via socket"""
    messages = []
    for call_args in mock_sock.sendall.call_args_list:
        msg = call_args[0][0].decode("utf-8").strip()
        messages.append(msg)
    return messages


def test_join_message_format(mock_client, setup_test_config):
    """
    JOIN must be :nick!~user@host JOIN :#channel
    - needs full user mask (nick!user@host)
    - needs colon before channel name
    - client won't switch to channel view without this exact format
    """
    client, mock_sock = mock_client

    # Setup registered client
    client.password = "ELSILRACLIHP"
    client.nickname = "testplayer"
    client.username = "test"
    client.realname = "48 0 US 3.8.1"
    client.registered = True

    # Process JOIN
    client.process_line("JOIN #heaven")

    # Check sent messages
    messages = get_sent_messages(mock_sock)
    join_msg = [m for m in messages if "JOIN" in m][0]

    # Verify format: :nick!~user@host JOIN :#channel
    pattern = r":testplayer!~test@127\.0\.0\.1 JOIN :#heaven"
    assert re.match(pattern, join_msg), f"JOIN format incorrect: {join_msg}"
    assert "JOIN :#heaven" in join_msg, "Missing colon before channel name"


def test_who_shows_actual_channel(mock_client, setup_test_config):
    """
    WHO response MUST show which channel users are in
    - must return actual channel (#heaven) not wildcard (*)
    """
    client, mock_sock = mock_client

    # Setup two clients in channel
    client.password = "ELSILRACLIHP"
    client.nickname = "player1"
    client.username = "test1"
    client.realname = "48 0 US 3.8.1"
    client.registered = True
    client.channels.add("#heaven")

    # Create second client
    mock_sock2 = Mock()
    client2 = IRCClient(mock_sock2, ("127.0.0.1", 12346))
    client2.nickname = "player2"
    client2.username = "test2"
    client2.realname = "48 0 GB 3.8.1"
    client2.registered = True
    client2.channels.add("#heaven")

    # Add both to state
    with state.irc_lock:
        state.irc_clients.append(client)
        state.irc_clients.append(client2)
        state.irc_channels["#heaven"]["users"].add("player1")
        state.irc_channels["#heaven"]["users"].add("player2")

    # Process WHO
    client.process_line("WHO #heaven")

    # Check responses
    messages = get_sent_messages(mock_sock)
    who_replies = [m for m in messages if " 352 " in m]

    assert len(who_replies) > 0, "WHO returned no results"

    # Verify shows #heaven not *
    for reply in who_replies:
        assert "#heaven" in reply, f"WHO doesn't show channel: {reply}"


def test_who_includes_realname(mock_client, setup_test_config):
    """
    WHO must include realname from USER command for country flags
    """
    client, mock_sock = mock_client

    # Setup client with realname
    client.password = "ELSILRACLIHP"
    client.nickname = "testplayer"
    client.username = "test"
    client.realname = "48 0 US 3.8.1"
    client.registered = True
    client.channels.add("#heaven")

    with state.irc_lock:
        state.irc_clients.append(client)
        state.irc_channels["#heaven"]["users"].add("testplayer")

    # Process WHO
    client.process_line("WHO #heaven")

    # Check response includes realname
    messages = get_sent_messages(mock_sock)
    who_reply = [m for m in messages if " 352 " in m][0]

    assert "48 0 US 3.8.1" in who_reply, f"WHO missing realname: {who_reply}"


def test_channel_topic_format(mock_client, setup_test_config):
    """
    Channel topic must be "icon topic" format (e.g. "00 Test Heaven")
    """
    client, mock_sock = mock_client

    # Setup registered client
    client.password = "ELSILRACLIHP"
    client.nickname = "testplayer"
    client.username = "test"
    client.registered = True

    # Process JOIN
    client.process_line("JOIN #heaven")

    # Check topic message
    messages = get_sent_messages(mock_sock)
    topic_msg = [m for m in messages if " 332 " in m][0]

    # Should have icon + space + topic
    assert re.search(r"00 Test Heaven", topic_msg), f"Topic format wrong: {topic_msg}"


def test_password_required(mock_client):
    """Registration should fail without correct password"""
    client, mock_sock = mock_client

    # Try to register without password
    client.nickname = "testplayer"
    client.username = "test"
    client.check_registration()

    # Should get error 464
    messages = get_sent_messages(mock_sock)
    error_msg = [m for m in messages if "464" in m][0]
    assert "464" in error_msg, f"Should get password error: {error_msg}"


def test_nickname_validation_valid(mock_client):
    """Valid nicknames should be accepted"""
    client, mock_sock = mock_client

    # Valid nickname
    client.process_line("PASS ELSILRACLIHP")
    client.process_line("NICK ValidNick123")
    client.process_line("USER test host server :48 0 US 3.8.1")

    assert client.nickname == "ValidNick123", "Valid nickname rejected"
    assert client.registered, "Registration failed with valid nickname"


def test_nickname_validation_invalid(mock_client):
    """Invalid nicknames should be rejected"""
    client, mock_sock = mock_client

    # Try invalid nickname (starts with number)
    client.process_line("PASS ELSILRACLIHP")
    client.process_line("NICK 123invalid")
    client.process_line("USER test host server :48 0 US 3.8.1")

    assert client.nickname is None, "Invalid nickname was accepted"
    assert not client.registered, "Registered with invalid nickname"


def test_realname_extraction(mock_client):
    """USER command should extract realname after colon"""
    client, mock_sock = mock_client

    client.process_line("USER testuser host server :48 0 US 3.8.1")

    assert client.username == "testuser"
    assert client.realname == "48 0 US 3.8.1", "Realname not extracted correctly"


def test_privmsg_to_channel(mock_client, setup_test_config):
    """PRIVMSG to channel should broadcast to other users"""
    client, mock_sock = mock_client

    # Setup sender
    client.nickname = "sender"
    client.username = "user1"
    client.registered = True
    client.channels.add("#heaven")

    # Setup receiver
    mock_sock2 = Mock()
    client2 = IRCClient(mock_sock2, ("127.0.0.1", 12346))
    client2.nickname = "receiver"
    client2.username = "user2"
    client2.registered = True
    client2.channels.add("#heaven")

    with state.irc_lock:
        state.irc_clients.append(client)
        state.irc_clients.append(client2)

    # Send message
    client.process_line("PRIVMSG #heaven :Hello everyone!")

    # Check receiver got it
    messages = get_sent_messages(mock_sock2)
    privmsg = [m for m in messages if "PRIVMSG" in m]
    assert len(privmsg) > 0, "Message not broadcast"
    assert "Hello everyone!" in privmsg[0], "Message content wrong"
