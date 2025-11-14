# hostingbuddy implementation guide

how to build an irc bot that creates worms armageddon game lobbies

## what is hostingbuddy

hostingbuddy is an irc bot that lets users create game lobbies via private message instead of port forwarding. user sends `host` to the bot, bot calls the http api to create a game listing, game appears in lobby.

## why you need it

worms uses direct peer-to-peer connections for games. this means:
- host needs port 17011 open
- host needs public ip or port forwarding
- many users can't do this (cgnat, mobile, restrictions)

hostingbuddy solves this by:
- running on server with public ip
- accepting host requests via irc privmsg
- creating game entries in the lobby list
- users can then join those games

## critical implementation details

### 1. game name format

**use dots, not spaces**

the worms client filters or rejects game names with spaces. use the official format:

```
Scheme.for.Nickname
```

examples:
- `Intermediate.for.shmup`
- `BnG.for.Player`
- `Shoppa.for.Alice`

**wrong:**
```python
name = f"{nick} game"        # spaces = invisible in lobby
name = f"{nick}'s game"      # spaces = invisible in lobby
```

**right:**
```python
name = f"{scheme}.for.{nick}"  # dots = shows up!
```

### 2. gamelist format

the `<GAME>` tag has **8 fields** in this exact order:

```
<GAME name host address location 1 password id type><BR>
```

field details:
1. **name** - game name (use dots not spaces)
2. **host** - player nickname
3. **address** - `ip:port` (e.g., `192.168.1.1:17011`)
4. **location** - location/flags code (usually `48` for US)
5. **mystery field** - **always `1`** (purpose unknown, but required!)
6. **password** - `1` if password protected, `0` if not
7. **id** - game id number
8. **type** - game type (`0` for normal)

**official example:**
```
<GAME Intermediate.for.shmup HostingBuddy hostingbuddy.wormnet.net:47083 48 1 0 4384298 0><BR>
```

**key finding:** field #5 is always `1` in official servers. if you put `0` or omit it, games won't show up.

### 3. irc privmsg handling

bot needs to handle both:
- **direct messages** - `:nick!user@ip PRIVMSG HostingBuddy :host`
- **channel mentions** - `:nick!user@ip PRIVMSG #channel :!host`

parse format:
```python
pattern = r':([^!]+)!([^@]+)@([^ ]+) PRIVMSG ([^ ]+) :!?(\w+)(.*)'
```

this captures:
- nick (sender)
- username
- ip (for creating game)
- target (channel or bot)
- command (with optional `!` prefix)
- args

### 4. game creation http api

**endpoint:** `GET /wormageddonweb/Game.asp`

**parameters:**
```python
{
    'Cmd': 'Create',
    'Name': 'Intermediate.for.shmup',  # use dots!
    'Nick': 'shmup',
    'HostIP': '192.168.50.1:17011',
    'Pwd': '',                          # empty for no password
    'Chan': 'hell',                     # channel name (no #)
    'Loc': '48',                        # location code
    'Type': '0',                        # game type
    'Scheme': 'Intermediate'            # optional scheme name
}
```

**response:**
```
SetGameId: 123
```

parse the id from response body (not header like old docs said):
```python
if response.status_code == 200 and 'SetGameId:' in response.text:
    game_id = int(response.text.split(':')[1].strip())
```

### 5. network addressing

**critical:** server must be accessible by public ip/hostname

**wrong config:**
```toml
[irc]
ip = "192.168.50.158"  # private ip - clients can't connect from internet!
```

**right config:**
```toml
[irc]
ip = "slime.green"     # public hostname
```

or:
```toml
[irc]
ip = "1.2.3.4"         # public ip
```

when clients connect, `Login.asp` tells them where the irc server is:
```
<CONNECT slime.green>
```

if you use a private ip here, only local network clients can connect.

### 6. game addressing (the hard part)

hostingbuddy creates games with the **client's ip** as the host address. this works if:
- client has public ip
- client has port forwarding set up
- client is on same network as other players

official wormnet solves this with relay servers:
```
hostingbuddy.wormnet.net:47083
```

this is a **proxy server** that relays game traffic. your simple hostingbuddy doesn't have this, so games only work if host is reachable.

### 7. bot user registration

bot connects to irc like any client:

```python
send_line(sock, 'PASS ELSILRACLIHP')
send_line(sock, 'NICK HostingBuddy')
send_line(sock, 'USER HostingBuddy host server :51 11 ZZ 3.8.1')
```

the `USER` realname field format:
```
:flags rank country version
```

example:
- `48 0 US 3.8.1` - normal client
- `51 11 ZZ 3.8.1` - bot (51 flags, rank 11, country ZZ)

### 8. response messages

keep responses simple:

```python
send_line(sock, f"PRIVMSG {user} :{user}: Game created (ID: {id})")
```

optional: use worms color codes (official bot uses `\p` and `\r` for colors, but not required)

## minimal working example

```python
#!/usr/bin/env python3
import re
import socket
import requests

def send_line(sock, line):
    sock.sendall(f'{line}\r\n'.encode('utf-8'))

def connect_irc(host='localhost', port=6667):
    sock = socket.socket()
    sock.connect((host, port))
    send_line(sock, 'PASS ELSILRACLIHP')
    send_line(sock, 'NICK HostingBuddy')
    send_line(sock, 'USER HostingBuddy host server :51 11 ZZ 3.8.1')
    return sock

def parse_privmsg(line):
    match = re.match(
        r':([^!]+)!([^@]+)@([^ ]+) PRIVMSG ([^ ]+) :!?(\w+)(.*)',
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

def create_game(nick, ip, channel, scheme='Intermediate'):
    url = 'http://localhost:8081/wormageddonweb/Game.asp'
    params = {
        'Cmd': 'Create',
        'Name': f"{scheme}.for.{nick}",  # use dots!
        'Nick': nick,
        'HostIP': f'{ip}:17011',
        'Pwd': '',
        'Chan': channel,
        'Loc': '48',
        'Type': '0',
        'Scheme': scheme
    }

    response = requests.get(url, params=params, timeout=5)
    if response.status_code == 200 and 'SetGameId:' in response.text:
        return int(response.text.split(':')[1].strip())
    return None

def run_bot():
    sock = connect_irc()
    send_line(sock, 'JOIN #hell')

    buffer = ''
    while True:
        data = sock.recv(4096).decode('utf-8', errors='ignore')
        if not data:
            break

        buffer += data
        lines = buffer.split('\r\n')
        buffer = lines[-1]

        for line in lines[:-1]:
            if not line:
                continue

            # handle ping
            if line.startswith('PING '):
                send_line(sock, line.replace('PING', 'PONG'))
                continue

            # handle host command
            msg = parse_privmsg(line)
            if msg and msg['command'] == 'host':
                game_id = create_game(msg['nick'], msg['ip'], 'hell')
                reply_to = msg['target'] if msg['target'].startswith('#') else msg['nick']

                if game_id:
                    send_line(sock, f"PRIVMSG {reply_to} :{msg['nick']}: Game created (ID: {game_id})")
                else:
                    send_line(sock, f"PRIVMSG {reply_to} :{msg['nick']}: Failed to create game")

if __name__ == '__main__':
    run_bot()
```

## testing

1. **start your wormnet server**
   ```bash
   python3 wormnet.py
   ```

2. **start hostingbuddy**
   ```bash
   python3 hostingbuddy.py
   ```

3. **connect worms client** (edit `WA.ini`)
   ```ini
   UseOfficialWormNET2=0
   OfficialWormNET2Address=yourserver.com/wormageddonweb/Login.asp
   ```

4. **in worms:**
   - join `#hell` channel
   - send private message to `HostingBuddy`: `host`
   - game should appear in lobby!

## troubleshooting

### games don't appear in lobby

check these in order:

1. **game name has spaces?**
   - fix: use dots instead (`Scheme.for.Nick`)

2. **gamelist format wrong?**
   - check field 5 is `1` (not `0`)
   - verify exact format: `<GAME name host addr loc 1 pwd id type><BR>`

3. **server using private ip?**
   - fix: set `ip = "public.hostname"` in `wormnet.toml`
   - restart server

4. **game expired?**
   - games timeout after 5 minutes
   - create a fresh one

5. **client can't reach http server?**
   - test: `curl http://yourserver/wormageddonweb/GameList.asp?Channel=hell`
   - should return game list

### bot doesn't respond

1. **bot connected to irc?**
   - check server logs for bot connection
   - verify bot joined channel

2. **privmsg regex not matching?**
   - test regex with sample lines
   - check for optional `!` prefix handling

3. **http api call failing?**
   - check bot debug output
   - verify http server url is correct

## advanced features

### multiple schemes

let users specify scheme:

```python
# parse: "host Shoppa" or just "host"
args = msg['args'].strip()
scheme = args if args else 'Intermediate'

game_id = create_game(msg['nick'], msg['ip'], channel, scheme)
```

### game tracking

track which user has which game:

```python
class GameState:
    def __init__(self):
        self.games = {}  # nick -> game_id

    def has_game(self, nick):
        return nick in self.games

    def store_game(self, nick, game_id):
        self.games[nick] = game_id

    def remove_game(self, nick):
        self.games.pop(nick, None)
```

prevent multiple games per user:

```python
if state.has_game(msg['nick']):
    send_line(sock, f"PRIVMSG {reply_to} :{msg['nick']}: Close your existing game first")
    return
```

### close command

let users remove their games:

```python
def close_game(game_id):
    url = 'http://localhost:8081/wormageddonweb/Game.asp'
    params = {'Cmd': 'Close', 'GameID': game_id}
    response = requests.get(url, params=params, timeout=5)
    return response.status_code == 200

# in bot loop:
if msg['command'] == 'close':
    game_id = state.get_game(msg['nick'])
    if game_id and close_game(game_id):
        state.remove_game(msg['nick'])
        send_line(sock, f"PRIVMSG {reply_to} :{msg['nick']}: Game closed")
```

### help command

```python
if msg['command'] == 'help':
    send_line(sock, f"PRIVMSG {reply_to} :Commands: host [scheme] - create game, close - remove game")
```

## differences from official

official wormnet's hostingbuddy:
- uses relay servers (`hostingbuddy.wormnet.net:47083`)
- handles nat traversal automatically
- supports complex game options
- integrates with account system

your simple hostingbuddy:
- uses client's actual ip
- requires client to be reachable (public ip or port forward)
- basic game creation only
- no authentication

this is fine for:
- local networks
- testing
- small private servers
- users who can port forward

## production improvements

for a real server, add:

1. **rate limiting** - prevent spam
2. **authentication** - verify users
3. **relay server** - proxy game traffic for nat users
4. **better error handling** - catch network failures
5. **logging** - track usage
6. **reconnect logic** - handle irc disconnects
7. **admin commands** - manage games remotely

## key takeaways

1. **game names: use dots not spaces**
2. **gamelist field 5: always `1`**
3. **server ip: must be public/reachable**
4. **response format: `SetGameId: 123` in body**
5. **client ip: comes from privmsg sender**

these five things are what makes hostingbuddy work. get them right and games will appear in the lobby!
