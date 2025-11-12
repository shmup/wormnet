"""http server for wormnet (game lobby management)"""
from flask import Flask, request, Response, send_from_directory
import time
import logging
from pathlib import Path
from . import state, config

app = Flask(__name__)


def cleanup_games():
    """remove expired games"""
    now = time.time()
    with state.games_lock:
        expired = [gid for gid, g in state.games.items()
                   if now - g['created'] > config.GAME_TIMEOUT]
        for gid in expired:
            del state.games[gid]


@app.route('/wormageddonweb/Login.asp')
def login():
    """tell client where irc server is"""
    # use configured IP if set, otherwise fall back to request host
    irc_host = config.IRC_HOST if config.IRC_HOST else request.host.split(':')[0]
    port_suffix = f":{config.CONNECT_PORT}" if config.CONNECT_PORT else ""
    response = f"<CONNECT {irc_host}{port_suffix}>"

    if config.NEWS_FILE and Path(config.NEWS_FILE).exists():
        try:
            news = Path(config.NEWS_FILE).read_text()
            response += f"\r\n<MOTD>\r\n{news}\r\n</MOTD>"
        except IOError:
            pass

    return response


@app.route('/wormageddonweb/RequestChannelScheme.asp')
def scheme():
    """return channel scheme"""
    chan = request.args.get('Channel')
    if chan and chan in config.CHANNELS:
        return f"<SCHEME={config.CHANNELS[chan]['scheme']}>"
    return "<NOTHING>"


@app.route('/wormageddonweb/Game.asp')
def game():
    """handle game creation/closing"""
    cmd = request.args.get('Cmd')
    cleanup_games()

    if cmd == 'Create':
        with state.games_lock:
            state.game_counter += 1
            state.games[state.game_counter] = {
                'id': state.game_counter,
                'name': request.args.get('Name', '')[:29],
                'host': request.args.get('Nick', ''),
                'address': request.args.get('HostIP', ''),
                'password': request.args.get('Pwd'),
                'channel': request.args.get('Chan', ''),
                'location': request.args.get('Loc', ''),
                'type': request.args.get('Type', '0'),
                'created': time.time(),
            }
            resp = Response("<NOTHING>")
            resp.headers['SetGameId'] = f": {state.game_counter}"
            return resp

    elif cmd == 'Close':
        gid = int(request.args.get('GameID', 0))
        with state.games_lock:
            if gid in state.games:
                del state.games[gid]
        return "<NOTHING>"

    elif cmd == 'Failed':
        return "<NOTHING>"

    return "<NOTHING>", 400


@app.route('/wormageddonweb/GameList.asp')
def gamelist():
    """list active games for channel"""
    cleanup_games()
    chan = request.args.get('Channel')

    lines = ["<GAMELISTSTART>\r\n"]
    with state.games_lock:
        for g in state.games.values():
            if g['channel'] == chan:
                pwd = 1 if g['password'] else 0
                lines.append(f"<GAME {g['name']} {g['host']} {g['address']} "
                             f"{g['location']} 1 {pwd} {g['id']} {g['type']}><BR>\r\n")
    lines.append("<GAMELISTEND>\r\n")

    return ''.join(lines)


@app.route('/wormageddonweb/UpdatePlayerInfo.asp')
def update_info():
    """no-op for player stats"""
    return "<NOTHING>"


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    """serve static files from wwwroot/"""
    wwwroot = Path(__file__).parent.parent / "wwwroot"
    if not wwwroot.exists():
        return "WormNET - Server Running", 200

    filepath = wwwroot / (path or "index.html")
    if filepath.exists() and filepath.is_file():
        return send_from_directory(wwwroot, path or "index.html")
    return "404", 404
