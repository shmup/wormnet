"""
Tests for WormNET HTTP endpoints

All endpoints are under /wormageddonweb/
"""

import pytest
from wormnet.http import app
from wormnet import state


@pytest.fixture
def client():
    """Create Flask test client"""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_login_endpoint(client):
    """
    Login.asp should return <CONNECT ip:port>
    This tells the client where the IRC server is
    """
    response = client.get("/wormageddonweb/Login.asp")
    assert response.status_code == 200
    text = response.get_data(as_text=True)

    # should contain CONNECT with ip:port
    assert "<CONNECT " in text, f"Missing CONNECT tag: {text}"
    assert ">" in text, f"Malformed CONNECT tag: {text}"

    # extract ip:port
    import re

    match = re.search(r"<CONNECT ([^>]+)>", text)
    assert match, f"Can't parse CONNECT: {text}"

    address = match.group(1)
    # may or may not have port depending on config
    if ":" in address:
        ip, port = address.split(":", 1)
        assert port.isdigit(), f"Invalid port: {port}"


def test_request_channel_scheme(client, setup_test_config):
    """
    RequestChannelScheme.asp?Channel=X should return <SCHEME=...>
    Format: <SCHEME=Pf,Be>
    """
    response = client.get("/wormageddonweb/RequestChannelScheme.asp?Channel=heaven")
    assert response.status_code == 200
    text = response.get_data(as_text=True)

    assert "<SCHEME=" in text, f"Missing SCHEME tag: {text}"
    assert ">" in text, f"Malformed SCHEME tag: {text}"


def test_request_unknown_channel_scheme(client):
    """Unknown channel should return <NOTHING>"""
    response = client.get(
        "/wormageddonweb/RequestChannelScheme.asp?Channel=nonexistent"
    )
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "<NOTHING>" in text


def test_game_create(client):
    """
    Game.asp?Cmd=Create should create a game and return SetGameId: N
    """
    response = client.get(
        "/wormageddonweb/Game.asp",
        query_string={
            "Cmd": "Create",
            "Name": "Test Game",
            "Nick": "TestPlayer",
            "HostIP": "1.2.3.4:17011",
            "Chan": "heaven",
            "Loc": "US",
            "Type": "0",
        },
    )

    assert response.status_code == 200

    # body should be <NOTHING>
    text = response.get_data(as_text=True)
    assert text == "<NOTHING>", f"Expected <NOTHING>, got: {text}"

    # SetGameId should be in header with format ": N"
    assert "SetGameId" in response.headers, "Missing SetGameId header"

    # extract game id from header (format is ": N")
    import re

    game_id_header = response.headers.get("SetGameId")
    match = re.search(r":\s*(\d+)", game_id_header)
    assert match, f"Can't parse game ID from header: {game_id_header}"

    game_id = int(match.group(1))
    assert game_id > 0, f"Invalid game ID: {game_id}"

    # verify game is in state
    assert game_id in state.games, "Game not added to state"
    game = state.games[game_id]
    assert game["name"] == "Test Game"
    assert game["host"] == "TestPlayer"
    assert game["channel"] == "heaven"


def test_game_list(client):
    """
    GameList.asp?Channel=X should return games in format:
    <GAME ...><BR>
    """
    # create a game first
    client.get(
        "/wormageddonweb/Game.asp",
        query_string={
            "Cmd": "Create",
            "Name": "Listed Game",
            "Nick": "Host1",
            "HostIP": "1.2.3.4:17011",
            "Chan": "heaven",
            "Loc": "US",
            "Type": "0",
        },
    )

    # now list games
    response = client.get("/wormageddonweb/GameList.asp?Channel=heaven")
    assert response.status_code == 200
    text = response.get_data(as_text=True)

    # should contain GAMELISTSTART/END
    assert "<GAMELISTSTART>" in text, f"Missing GAMELISTSTART: {text}"
    assert "<GAMELISTEND>" in text, f"Missing GAMELISTEND: {text}"

    # should contain game info
    assert "GAME" in text, f"No games in list: {text}"
    assert "Listed Game" in text, f"Created game not in list: {text}"
    assert "Host1" in text, f"Host not in game list: {text}"


def test_game_close(client):
    """
    Game.asp?Cmd=Close&GameID=N should remove the game
    """
    # create a game
    response = client.get(
        "/wormageddonweb/Game.asp",
        query_string={
            "Cmd": "Create",
            "Name": "Temp Game",
            "Nick": "TempHost",
            "HostIP": "1.2.3.4:17011",
            "Chan": "heaven",
            "Loc": "US",
            "Type": "0",
        },
    )

    import re

    game_id_header = response.headers.get("SetGameId")
    match = re.search(r":\s*(\d+)", game_id_header)
    game_id = int(match.group(1))

    # verify it exists
    assert game_id in state.games, "Game wasn't created"

    # close it
    response = client.get(f"/wormageddonweb/Game.asp?Cmd=Close&GameID={game_id}")
    assert response.status_code == 200

    # verify it's gone
    assert game_id not in state.games, "Game wasn't removed"


def test_game_list_empty_channel(client):
    """
    GameList.asp for channel with no games should return valid response
    """
    response = client.get("/wormageddonweb/GameList.asp?Channel=AnythingGoes")
    assert response.status_code == 200
    text = response.get_data(as_text=True)

    # should have list markers
    assert "<GAMELISTSTART>" in text
    assert "<GAMELISTEND>" in text


def test_game_name_length_limit(client):
    """
    Game names should be limited to 29 characters (from what.txt)
    """
    long_name = "A" * 50  # longer than 29

    response = client.get(
        "/wormageddonweb/Game.asp",
        query_string={
            "Cmd": "Create",
            "Name": long_name,
            "Nick": "TestPlayer",
            "HostIP": "1.2.3.4:17011",
            "Chan": "heaven",
            "Loc": "US",
            "Type": "0",
        },
    )

    import re

    game_id_header = response.headers.get("SetGameId")
    match = re.search(r":\s*(\d+)", game_id_header)
    game_id = int(match.group(1))

    # check that name was truncated
    game = state.games[game_id]
    assert len(game["name"]) <= 29, f"Game name too long: {len(game['name'])}"


def test_private_game_type(client):
    """
    Type=1 should create private game (password protected)
    """
    response = client.get(
        "/wormageddonweb/Game.asp",
        query_string={
            "Cmd": "Create",
            "Name": "Private Game",
            "Nick": "PrivateHost",
            "HostIP": "1.2.3.4:17011",
            "Chan": "heaven",
            "Loc": "US",
            "Type": "1",  # private
        },
    )

    import re

    game_id_header = response.headers.get("SetGameId")
    match = re.search(r":\s*(\d+)", game_id_header)
    game_id = int(match.group(1))

    game = state.games[game_id]
    assert game["type"] == "1", "Game should be private (type=1)"


def test_update_player_info_noop(client):
    """UpdatePlayerInfo.asp should be a no-op"""
    response = client.get("/wormageddonweb/UpdatePlayerInfo.asp")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "<NOTHING>" in text
