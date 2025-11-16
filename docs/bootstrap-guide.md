# wormnet server bootstrap guide

build your own wormnet server in any language. tested protocol, works with worms armageddon.

## minimum requirements

### 1. irc server (port 6667)

implement a subset of rfc 1459/2812:

**required commands:**
- `PASS` - server password authentication
- `NICK` - set/change nickname
- `USER` - user registration (username, hostname, servername, realname)
- `PING` / `PONG` - keepalive
- `JOIN` - join channels
- `PART` - leave channels
- `PRIVMSG` - send messages (to channels or users)
- `QUIT` - disconnect
- `LIST` - list channels
- `NAMES` - list users in channel
- `WHO` - query user info
- `MODE` - query/set channel modes (can be minimal)
- `MOTD` - message of the day

**optional but nice:**
- `WHOIS` - detailed user info
- `TOPIC` - view/set channel topic
- `OPER` - operator privileges

**server password:**
```
ELSILRACLIHP
```
(this is "PHILCARLIS" backwards - must be hardcoded, game requires it)

**registration flow:**
```
client -> PASS ELSILRACLIHP
client -> NICK PlayerName
client -> USER username hostname servername :realname
server -> :server 001 PlayerName :Welcome, PlayerName!
server -> :server 375 PlayerName :- server Message of the Day -
server -> :server 372 PlayerName :- [motd lines]
server -> :server 376 PlayerName :End of /MOTD command.
```

**channel behavior:**
- channels start with `#` (e.g., `#AnythingGoes`)
- channel topics formatted as: `XX description` where XX is 2-digit icon number
- users can join, part, send messages
- no op requirements for worms (can skip mode enforcement if you want)

**nickname validation:**
- pattern: `^[a-zA-Z][a-zA-Z0-9\-\`\|\[\]\{\}_^]{0,14}$`
- max 15 characters
- must start with letter

### 2. http server (port 80)

implement these asp-style endpoints under `/wormageddonweb/`:

#### `Login.asp`

**IMPORTANT:** Server list links MUST point directly to `/wormageddonweb/Login.asp`. The client caches server addresses and will skip this endpoint on reconnect if your link points to the root URL, causing a blue screen hang.

**correct link:** `http://yourserver.com/wormageddonweb/Login.asp`
**wrong link:** `http://yourserver.com` (client will blue screen on reconnect)

**request:** `GET /wormageddonweb/Login.asp`

**response:**
```
<CONNECT server_ip:irc_port>
```

if port is 6667, omit the `:6667` part (game assumes it). if you have news:

```
<CONNECT server_ip:irc_port>
<MOTD>
[html news content]
</MOTD>
```

**example:**
```
<CONNECT 192.168.1.100>
<MOTD>
<body BGCOLOR="DarkBlue"><CENTER>
<FONT SIZE="4" COLOR="Yellow">N E W S</FONT><BR>
<FONT SIZE="2" COLOR="White">Welcome to my server!</FONT><BR>
</CENTER>
</MOTD>
```

#### `RequestChannelScheme.asp`

**request:** `GET /wormageddonweb/RequestChannelScheme.asp?Channel=AnythingGoes`

**response:**
```
<SCHEME=Pf,Be>
```

scheme format is comma-separated codes. examples:
- `Pf,Be` - party, full wormage / bazooka, elite
- `Pa,Ba` - party, auto / bazooka, auto
- see http://worms2d.info/WormNET for full list

#### `Game.asp` - Create

**request:** `GET /wormageddonweb/Game.asp?Cmd=Create&Name=My%20Game&Nick=Player1&HostIP=192.168.1.50:17011&Chan=AnythingGoes&Loc=US&Type=0`

**parameters:**
- `Cmd=Create`
- `Name` - game name (truncate to 29 chars)
- `Nick` - host nickname
- `HostIP` - host ip:port for direct connect
- `Pwd` - optional password
- `Chan` - channel name (without #)
- `Loc` - location code (country/region)
- `Type` - game type code (usually 0)

**response body:**
```
<NOTHING>
```

**response header:**
```
SetGameId: : 123
```
(note: the header format is `SetGameId: : 123` with a space-colon-space before the ID)

store this game in memory with auto-incrementing id. expire games after 5 minutes.

#### `Game.asp` - Close

**request:** `GET /wormageddonweb/Game.asp?Cmd=Close&GameID=123`

**response:**
```
<NOTHING>
```

remove game from memory.

#### `Game.asp` - Failed

**request:** `GET /wormageddonweb/Game.asp?Cmd=Failed`

**response:**
```
<NOTHING>
```

no-op, just return success.

#### `GameList.asp`

**request:** `GET /wormageddonweb/GameList.asp?Channel=AnythingGoes`

**response:**
```
<GAMELISTSTART>
<GAME My Game Player1 192.168.1.50:17011 US 1 0 123 0><BR>
<GAME Another Game Player2 192.168.1.51:17011 CA 1 1 124 0><BR>
<GAMELISTEND>
```

**format:** `<GAME name host ip location open password id type><BR>`
- `name` - game name
- `host` - host nickname
- `ip` - ip:port
- `location` - location code
- `open` - 1 if joinable, 0 if full/started
- `password` - 1 if passworded, 0 if not
- `id` - game id
- `type` - game type

**implementation notes:**
- client sends `Channel` parameter but you can return all games regardless of channel (simpler for small servers)
- alternatively, filter by `g['channel'] == chan` to only show games for requested channel
- always remove expired games (5 min old) before returning list

#### `UpdatePlayerInfo.asp`

**request:** `GET /wormageddonweb/UpdatePlayerInfo.asp?[various params]`

**response:**
```
<NOTHING>
```

no-op, game tries to send stats but we ignore them.

### 3. static file serving

serve files from a `wwwroot/` directory for any path not matching above endpoints.

example: `GET /index.html` serves `wwwroot/index.html`

## data structures

### game object

```python
class Game:
    id: int              # auto-incrementing
    name: str            # max 29 chars
    host: str            # nickname
    address: str         # ip:port
    password: str | None # optional
    channel: str         # channel name
    location: str        # location code
    type: str            # game type
    created: datetime    # for expiration
```

### channel object

```python
class Channel:
    name: str        # e.g., "AnythingGoes"
    topic: str       # e.g., "Anything goes!"
    icon: int        # 00-99
    scheme: str      # e.g., "Pf,Be"
```

irc channel name = `#` + channel name
irc channel topic = `f"{icon:02d} {topic}"`

## pseudocode implementation

### python/flask example

```python
from flask import Flask, request
import time

app = Flask(__name__)

# config
IRC_HOST = "192.168.1.100"
IRC_PORT = 6667
CHANNELS = {
    "AnythingGoes": {"topic": "Anything goes!", "icon": 0, "scheme": "Pf,Be"},
    "PartyTime": {"topic": "Party time!", "icon": 0, "scheme": "Pa,Ba"},
}

# game storage
games = {}
game_counter = 0
GAME_TIMEOUT = 300  # 5 minutes

def cleanup_games():
    now = time.time()
    expired = [gid for gid, g in games.items() if now - g['created'] > GAME_TIMEOUT]
    for gid in expired:
        del games[gid]

@app.route('/wormageddonweb/Login.asp')
def login():
    connect = f"<CONNECT {IRC_HOST}>"
    if IRC_PORT != 6667:
        connect = f"<CONNECT {IRC_HOST}:{IRC_PORT}>"
    # optional: add <MOTD>news</MOTD>
    return connect

@app.route('/wormageddonweb/RequestChannelScheme.asp')
def scheme():
    chan = request.args.get('Channel')
    if chan in CHANNELS:
        return f"<SCHEME={CHANNELS[chan]['scheme']}>"
    return "<NOTHING>"

@app.route('/wormageddonweb/Game.asp')
def game():
    from flask import Response
    cmd = request.args.get('Cmd')
    cleanup_games()

    if cmd == 'Create':
        global game_counter
        game_counter += 1
        games[game_counter] = {
            'id': game_counter,
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
        resp.headers['SetGameId'] = f": {game_counter}"
        return resp

    elif cmd == 'Close':
        gid = int(request.args.get('GameID', 0))
        if gid in games:
            del games[gid]
        return "<NOTHING>"

    elif cmd == 'Failed':
        return "<NOTHING>"

    return "<NOTHING>", 400

@app.route('/wormageddonweb/GameList.asp')
def gamelist():
    cleanup_games()
    chan = request.args.get('Channel')

    lines = ["<GAMELISTSTART>\r\n"]
    for g in games.values():
        if g['channel'] == chan:
            pwd = 1 if g['password'] else 0
            lines.append(
                f"<GAME {g['name']} {g['host']} {g['address']} "
                f"{g['location']} 1 {pwd} {g['id']} {g['type']}><BR>\r\n"
            )
    lines.append("<GAMELISTEND>\r\n")

    return ''.join(lines)

@app.route('/wormageddonweb/UpdatePlayerInfo.asp')
def update_info():
    return "<NOTHING>"

# serve static files from wwwroot/
@app.route('/<path:path>')
def static_files(path):
    return flask.send_from_directory('wwwroot', path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
```

### irc server (python twisted example)

```python
from twisted.words.protocols import irc
from twisted.internet import protocol, reactor

PASSWORD = "ELSILRACLIHP"

class WormNetIRC(irc.IRC):
    def connectionMade(self):
        self.nickname = None
        self.username = None
        self.registered = False
        self.password = None
        self.channels = set()

    def irc_PASS(self, prefix, params):
        if params:
            self.password = params[0]

    def irc_NICK(self, prefix, params):
        if not params:
            return
        nick = params[0]
        # validate nickname...
        self.nickname = nick
        self.checkRegistration()

    def irc_USER(self, prefix, params):
        if len(params) >= 4:
            self.username = params[0]
            self.checkRegistration()

    def checkRegistration(self):
        if self.nickname and self.username and not self.registered:
            if self.password != PASSWORD:
                self.sendLine(f":{self.hostname} 464 * :Password incorrect")
                return
            self.registered = True
            self.sendLine(f":{self.hostname} 001 {self.nickname} :Welcome!")
            # send more registration messages...
            self.sendMOTD()

    def irc_JOIN(self, prefix, params):
        if not self.registered:
            return
        for channame in params[0].split(','):
            if channame.startswith('#'):
                self.channels.add(channame)
                # send join confirmation, topic, names list...

    def irc_PRIVMSG(self, prefix, params):
        if not self.registered or len(params) < 2:
            return
        target, message = params[0], params[1]
        # relay to target channel/user...

    # implement other commands...

class WormNetFactory(protocol.ServerFactory):
    protocol = WormNetIRC

reactor.listenTCP(6667, WormNetFactory())
reactor.run()
```

## testing your server

### 1. test http endpoints

```bash
# test login
curl http://localhost/wormageddonweb/Login.asp

# test scheme
curl http://localhost/wormageddonweb/RequestChannelScheme.asp?Channel=AnythingGoes

# test game creation
curl "http://localhost/wormageddonweb/Game.asp?Cmd=Create&Name=Test&Nick=Player&HostIP=1.2.3.4:17011&Chan=AnythingGoes&Loc=US&Type=0" -v

# test game list
curl http://localhost/wormageddonweb/GameList.asp?Channel=AnythingGoes
```

### 2. test irc with telnet

```bash
telnet localhost 6667
PASS ELSILRACLIHP
NICK TestPlayer
USER test hostname servername :Real Name
JOIN #AnythingGoes
PRIVMSG #AnythingGoes :Hello!
LIST
QUIT :bye
```

### 3. test with worms armageddon

in worms:
1. open `C:\Team17\Worms Armageddon\Users\[name]\WA.ini`
2. change:
```ini
UseOfficialWormNET2=0
OfficialWormNET2Address=your.server.ip
```
3. restart game
4. click "WormNET" button
5. should connect to your server!

## scheme codes reference

format: `TypeExtra,TypeExtra,...`

**game types:**
- `B` - bazooka & grenade
- `N` - normal
- `P` - party
- `S` - shoppa
- `T` - team17
- `W` - worms + weapons

**extras:**
- `a` - auto
- `e` - elite
- `f` - full wormage
- `p` - pro

examples:
- `Pf,Be` - party full, bazooka elite
- `Pa,Ba` - party auto, bazooka auto
- `Nf,Sf` - normal full, shoppa full

full list: http://worms2d.info/WormNET

## common issues

### game won't connect
- check password is exactly `ELSILRACLIHP`
- check port 6667 is open
- check IRC server sends proper welcome messages

### games don't appear
- check GameList.asp returns proper format
- check games aren't expiring too fast
- check channel name matches (case-sensitive in some places)

### news doesn't show
- check `<MOTD>` tags are present in Login.asp response
- html must be in old-school format (BGCOLOR, FONT tags)
- keep it simple, game's html parser is basic

## production considerations

what this minimal guide skips (but you should add):

- **tls/ssl** - encrypt connections (game doesn't support, but good practice)
- **authentication** - verify users
- **rate limiting** - prevent spam/abuse
- **input validation** - sanitize all inputs
- **database** - persist games and users
- **logging** - track activity
- **metrics** - monitor usage
- **ip banning** - block bad actors
- **flood protection** - limit message rate
- **channel modes** - enforce +m, +k, +b etc
- **oper commands** - kick, ban, kill users

## alternative implementations

### node.js

use:
- `express` for http
- `irc-framework` or write custom irc server
- `node-cache` for game storage

### bun

same as node.js but faster:
```bash
bun install express
bun run server.js
```

### python/uv

use:
- `flask` or `fastapi` for http
- `twisted` or custom irc using `asyncio`
- `redis` for game storage

```bash
uv pip install flask twisted
uv run server.py
```

### rust

use:
- `actix-web` for http
- custom irc with `tokio`
- in-memory hashmap for games

### go

use:
- `net/http` stdlib
- `ergochat/irc-go` for irc helpers
- map for game storage

## minimal line counts

you can build a working wormnet server in:
- python: ~300 lines (http + basic irc)
- javascript: ~250 lines
- go: ~350 lines
- rust: ~400 lines

the protocol is simple because:
1. no game state on server
2. minimal irc subset
3. simple text responses
4. no encryption/auth required
5. clients are well-behaved

## next steps

once you have basic server working:

1. **add channels** - create interesting themes
2. **customize news** - welcome message, rules
3. **style wwwroot** - make a nice homepage
4. **add stats** - track popular games
5. **add discord** - bridge irc to discord
6. **add bots** - helpful commands
7. **add web ui** - show online users/games

## reference implementation

this wormnet codebase is a complete python reference. key files:
- `wormnet/config.py` - configuration loading and channel setup
- `wormnet/http.py` - all http endpoints (Login, Game, GameList, etc)
- `wormnet/irc.py` - irc server implementation with IRCClient class
- `wormnet/state.py` - shared state for games and clients

for other implementations, use an irc library or implement the commands listed in the irc server section above.

## help and resources

- worms2d.info/WormNET - official protocol docs
- rfc 1459 - irc protocol spec
- github.com/cybershadow/mywormnet2 - original implementation
- worms armageddon discord - community help

good luck building your wormnet!
