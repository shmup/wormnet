"""
Tests for WormNET IRC protocol compliance

Based on gotchas from what.txt - these are critical for client compatibility
"""

import pytest
import re
import time


def test_join_message_format(irc_client):
    """
    JOIN must be :nick!~user@host JOIN :#channel
    - needs full user mask (nick!user@host)
    - needs colon before channel name
    - client won't switch to channel view without this exact format
    """
    # authenticate
    irc_client.send("PASS ELSILRACLIHP")
    irc_client.send("NICK testplayer")
    irc_client.send("USER test host server :48 0 US 3.8.1")

    # clear welcome messages
    irc_client.recv_until("376")  # end of MOTD

    # join channel
    irc_client.send("JOIN #heaven")
    lines = irc_client.recv_until("366")  # end of NAMES

    # find the JOIN line
    join_line = None
    for line in lines:
        if "JOIN" in line:
            join_line = line
            break

    assert join_line is not None, "No JOIN response received"

    # verify format: :nick!~user@host JOIN :#channel
    # pattern: :testplayer!~test@127.0.0.1 JOIN :#heaven
    pattern = r":testplayer!~test@[\d\.]+ JOIN :#heaven"
    assert re.match(
        pattern, join_line
    ), f"JOIN format incorrect: {join_line}\nExpected: :nick!~user@host JOIN :#channel"

    # specifically check for colon before channel
    assert "JOIN :#heaven" in join_line, "Missing colon before channel name in JOIN"


def test_who_shows_actual_channel(irc_client):
    """
    WHO response MUST show which channel users are in
    - format: 352 nick #channel ~user host server nick H :0 realname
    - must return actual channel (#heaven) not wildcard (*)
    - empty WHO (just 315 end) = client hangs waiting
    """
    # authenticate and join
    irc_client.send("PASS ELSILRACLIHP")
    irc_client.send("NICK testplayer")
    irc_client.send("USER test host server :48 0 US 3.8.1")
    irc_client.recv_until("376")
    irc_client.send("JOIN #heaven")
    irc_client.recv_until("366")

    # send WHO
    irc_client.send("WHO #heaven")
    lines = irc_client.recv_until("315")  # end of WHO

    # find 352 responses (RPL_WHOREPLY)
    who_replies = [l for l in lines if " 352 " in l]
    assert len(who_replies) > 0, "WHO returned no results - client will hang!"

    # check that channel is #heaven not *
    for reply in who_replies:
        assert "#heaven" in reply, f"WHO shows wildcard (*) instead of channel: {reply}"
        assert (
            " * " not in reply or "#heaven" in reply
        ), f"WHO shows * instead of #heaven: {reply}"


def test_who_includes_realname_from_user_command(irc_client):
    """
    USER command contains country/flags in realname
    - format: USER username host server :flags rank country version
    - extract everything after : and return in WHO replies
    - without this, client shows ? instead of country flags
    """
    # authenticate with specific realname containing country
    irc_client.send("PASS ELSILRACLIHP")
    irc_client.send("NICK testplayer")
    realname = "48 0 US 3.8.1"
    irc_client.send(f"USER test host server :{realname}")
    irc_client.recv_until("376")
    irc_client.send("JOIN #heaven")
    irc_client.recv_until("366")

    # send WHO
    irc_client.send("WHO #heaven")
    lines = irc_client.recv_until("315")

    # find our WHO reply
    who_replies = [l for l in lines if " 352 " in l and "testplayer" in l]
    assert len(who_replies) > 0, "No WHO reply for our user"

    # verify realname is included
    who_reply = who_replies[0]
    assert realname in who_reply, f"WHO doesn't include realname from USER: {who_reply}"


def test_channel_topic_format(irc_client):
    """
    Channel topics must match expected format
    - topic for #heaven should be "00 Test Heaven" (icon + space + name)
    - custom topics break client expectations
    """
    # authenticate and join
    irc_client.send("PASS ELSILRACLIHP")
    irc_client.send("NICK testplayer")
    irc_client.send("USER test host server :48 0 US 3.8.1")
    irc_client.recv_until("376")
    irc_client.send("JOIN #heaven")
    lines = irc_client.recv_until("366")

    # Debug: print all lines received
    all_text = "\n".join(lines)

    # find topic (332 RPL_TOPIC)
    topic_lines = [l for l in lines if " 332 " in l]
    assert len(topic_lines) > 0, f"No topic sent for channel. Received:\n{all_text}"

    topic_line = topic_lines[0]
    # topic should contain "00 Test Heaven" (icon + space + text)
    assert re.search(
        r"00 Test Heaven", topic_line
    ), f"Topic format incorrect: {topic_line}"


def test_password_required(irc_client):
    """PASS ELSILRACLIHP is required before registration completes"""
    # try to connect without password - send both NICK and USER to trigger registration
    irc_client.send("NICK testplayer")
    irc_client.send("USER test host server :48 0 US 3.8.1")

    # Should get 464 error about incorrect password, then connection closes
    line = irc_client.recv_line()
    assert "464" in line, f"Should get password error (464), got: {line}"


def test_multiple_clients_in_channel(irc_client, irc_server):
    """
    WHO should return all users in channel
    Tests that multiple clients are tracked properly
    """
    # first client joins
    irc_client.send("PASS ELSILRACLIHP")
    irc_client.send("NICK player1")
    irc_client.send("USER test1 host server :48 0 US 3.8.1")
    irc_client.recv_until("376")
    irc_client.send("JOIN #heaven")
    irc_client.recv_until("366")

    # create second client
    from tests.conftest import IRCTestClient

    host, port = irc_server
    client2 = IRCTestClient(host, port)
    client2.connect()

    client2.send("PASS ELSILRACLIHP")
    client2.send("NICK player2")
    client2.send("USER test2 host server :48 0 GB 3.8.1")
    client2.recv_until("376")
    client2.send("JOIN #heaven")
    client2.recv_until("366")

    # first client sends WHO
    irc_client.send("WHO #heaven")
    lines = irc_client.recv_until("315")

    # should see both players
    who_replies = [l for l in lines if " 352 " in l]
    assert len(who_replies) >= 2, f"WHO should show both users, got {len(who_replies)}"

    who_text = "\n".join(who_replies)
    assert "player1" in who_text, "player1 not in WHO response"
    assert "player2" in who_text, "player2 not in WHO response"

    client2.close()


def test_client_flow_sequence(irc_client):
    """
    Test the complete client flow from what.txt:
    RequestChannelScheme → JOIN → WHO → GameList.asp
    - if WHO is wrong, client never requests GameList.asp
    - if JOIN is wrong, client shows "joined" but stays on channel list
    """
    # authenticate
    irc_client.send("PASS ELSILRACLIHP")
    irc_client.send("NICK testplayer")
    irc_client.send("USER test host server :48 0 US 3.8.1")
    irc_client.recv_until("376")

    # JOIN
    irc_client.send("JOIN #heaven")
    join_lines = irc_client.recv_until("366")

    # verify JOIN format
    join_msg = [l for l in join_lines if "JOIN" in l and "testplayer" in l]
    assert len(join_msg) > 0, "No JOIN message"
    assert re.search(
        r":testplayer!~test@[\d\.]+ JOIN :#heaven", join_msg[0]
    ), f"JOIN format wrong: {join_msg[0]}"

    # WHO
    irc_client.send("WHO #heaven")
    who_lines = irc_client.recv_until("315")

    # verify WHO has results
    who_replies = [l for l in who_lines if " 352 " in l]
    assert len(who_replies) > 0, "WHO returned no results - client will hang!"

    # verify WHO shows channel
    who_text = "\n".join(who_replies)
    assert (
        "#heaven" in who_text
    ), "WHO doesn't show channel - client won't proceed to GameList"


def test_nickname_validation(irc_client):
    r"""
    Nickname pattern: ^[a-zA-Z][a-zA-Z0-9\-`|\[\]\{\}_^]{0,14}$
    - must start with letter
    - max 15 chars
    - only allowed special chars
    """
    irc_client.send("PASS ELSILRACLIHP")
    irc_client.send("NICK ValidNick")
    irc_client.send("USER test host server :48 0 US 3.8.1")

    # Should get welcome messages (001-005), no errors
    lines = irc_client.recv_until("376")  # end of MOTD

    # check for welcome (001) and no errors (432/433)
    all_text = "\n".join(lines)
    assert " 001 " in all_text, f"No welcome message, got: {all_text}"
    assert (
        "432" not in all_text and "433" not in all_text
    ), f"Valid nickname rejected: {all_text}"
