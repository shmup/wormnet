# wormnet debugging cheatsheet

## packet capture

### capture traffic
```bash
# capture all wormnet traffic (both http + irc)
sudo tcpdump -i any -w wormnet-capture.pcap 'host wormnet1.team17.com' -v

# capture local wormhole traffic
sudo tcpdump -i any -w wormhole-capture.pcap 'port 6667 or port 8081' -v

# capture specific port
sudo tcpdump -i any -w http-only.pcap 'port 80' -v
sudo tcpdump -i any -w irc-only.pcap 'port 6667' -v
```

### analyze captures
```bash
# open in wireshark
wireshark wormnet-capture.pcap

# view as text with ascii
tcpdump -r wormnet-capture.pcap -A

# extract irc payloads (port 6667)
tshark -r wormnet-capture.pcap -Y "tcp.port == 6667" -T fields -e tcp.payload | xxd -r -p > irc.txt

# extract http payloads (port 80)
tshark -r wormnet-capture.pcap -Y "tcp.port == 80" -T fields -e tcp.payload | xxd -r -p > http.txt

# follow tcp stream
tshark -r wormnet-capture.pcap -q -z follow,tcp,ascii,0 > stream.txt
```

## http endpoints

### team17 official (wormnet1.team17.com)

```bash
# login - get irc server info
curl "http://wormnet1.team17.com/wormageddonweb/Login.asp?Username&Password"
# returns: <CONNECT wormnet1.team17.com:6667>

# create game
curl "http://wormnet1.team17.com/wormageddonweb/Game.asp?Cmd=Create&Name=TestGame&Nick=Player1&HostIP=1.2.3.4:17011&Chan=AnythingGoes&Loc=US&Type=0&Scheme=Pf,Be" -v
# returns: <NOTHING> (body) with header "SetGameId: : 12345" (note the double colon)

# close game
curl "http://wormnet1.team17.com/wormageddonweb/Game.asp?Cmd=Close&GameID=12345"
# returns: <NOTHING>

# list games for channel
curl "http://wormnet1.team17.com/wormageddonweb/GameList.asp?Channel=AnythingGoes"
# returns:
# <GAMELISTSTART>
# <GAME GameName Host 1.2.3.4:17011 US 1 0 12345 0><BR>
# <GAMELISTEND>

# get channel scheme
curl "http://wormnet1.team17.com/wormageddonweb/RequestChannelScheme.asp?Channel=AnythingGoes"
# returns: <SCHEME=Pf,Be>

# update player info (no-op)
curl "http://wormnet1.team17.com/wormageddonweb/UpdatePlayerInfo.asp"
# returns: <NOTHING>
```

### wormhole local (slime.green:8081 or localhost:8081)

```bash
# login
curl "http://slime.green:8081/wormageddonweb/Login.asp"
curl "http://localhost:8081/wormageddonweb/Login.asp"
# returns: <CONNECT slime.green:6667>  (or localhost)

# create game
curl "http://slime.green:8081/wormageddonweb/Game.asp?Cmd=Create&Name=TestGame&Nick=Player1&HostIP=1.2.3.4:17011&Chan=AnythingGoes&Loc=US&Type=0&Scheme=Pf,Be" -v
# returns: <NOTHING> (body) with header "SetGameId: : 1" (note the double colon)

# close game
curl "http://slime.green:8081/wormageddonweb/Game.asp?Cmd=Close&GameID=1"
# returns: <NOTHING>

# list games for channel
curl "http://slime.green:8081/wormageddonweb/GameList.asp?Channel=AnythingGoes"
curl "http://localhost:8081/wormageddonweb/GameList.asp?Channel=AnythingGoes"
# returns:
# <GAMELISTSTART>
# <GAME GameName Host 1.2.3.4:17011 US 1 0 1 0><BR>
# <GAMELISTEND>

# get channel scheme
curl "http://slime.green:8081/wormageddonweb/RequestChannelScheme.asp?Channel=AnythingGoes"
# returns: <SCHEME=Pf,Be>
```

## irc testing

### connect to team17 wormnet1
```bash
telnet wormnet1.team17.com 6667
```

### connect to wormhole local
```bash
telnet localhost 6667
telnet slime.green 6667
```

### irc command sequence
```
PASS ELSILRACLIHP
NICK TestPlayer
USER test host server :48 0 US 3.8.1
JOIN #AnythingGoes
LIST
NAMES #AnythingGoes
WHO #AnythingGoes
PRIVMSG #AnythingGoes :hello world
QUIT
```

### using hostingbuddy
```bash
# connect to wormhole
python3 hostingbuddy.py --host localhost --port 6667 --log-level DEBUG

# connect to team17
python3 hostingbuddy.py --host wormnet1.team17.com --port 6667 --log-level DEBUG

# test commands in irc channel
!host           # create game
!close          # close game
```

## running local servers

### start wormhole
```bash
python3 wormnet.py
# or with config
python3 wormnet.py -c config.ini
```

### test with real client
1. edit hosts file: `127.0.0.1 wormnet1.team17.com`
2. launch WA.exe
3. go to wormnet
4. observe logs in wormnet.py terminal

## game creation parameters

### Game.asp?Cmd=Create parameters
- **Name**: game name (max 29 chars) - shown in lobby
- **Nick**: host nickname
- **HostIP**: host ip:port (usually x.x.x.x:17011)
- **Pwd**: password (empty string for no password)
- **Chan**: channel name (without #)
- **Loc**: location/flags (48 is common, 2-digit hex)
- **Type**: game type (0=normal, 1=ranked, etc)
- **Scheme**: scheme code (e.g., Pf,Be or Intermediate)

### GameList response format
```
<GAME {name} {host} {hostip} {loc} 1 {pwd} {gameid} {type}><BR>
```
- pwd: 1 if password set, 0 if no password
- middle "1" is unknown (always 1?)

## common issues to check

### http responses
- [ ] Login.asp returns <CONNECT host:port>
- [ ] Game.asp Create returns "SetGameId: N" (with space after colon)
- [ ] GameList starts with <GAMELISTSTART>\r\n
- [ ] GameList ends with <GAMELISTEND>\r\n
- [ ] Each game line has <BR>\r\n
- [ ] Scheme format is Type,Type (e.g., Pf,Be)

### irc protocol
- [ ] PASS must be ELSILRACLIHP
- [ ] Lines end with \r\n
- [ ] JOIN notification sent to channel
- [ ] WHO returns proper realname (flags rank country version)
- [ ] PRIVMSG format: :nick!user@host PRIVMSG target :message

### game hosting issues
- [ ] HostIP includes :17011 port
- [ ] Channel name matches exactly (case sensitive?)
- [ ] Game shows in GameList for correct channel
- [ ] Game timeout cleanup (5 minutes)

## debugging workflow

1. **capture packets** from working client → team17 server
2. **extract http/irc** payloads from pcap
3. **compare responses** between team17 and wormhole
4. **test endpoints** manually with curl
5. **check logs** in wormnet.py and hostingbuddy.py
6. **verify protocol** details (line endings, spacing, format)

## useful filters in wireshark

- `tcp.port == 6667` - irc traffic
- `tcp.port == 80 or tcp.port == 8081` - http traffic
- `http.request.uri contains "Game.asp"` - game operations
- `http.request.uri contains "GameList.asp"` - game list requests
- `tcp.stream eq 0` - follow specific tcp connection

## quick reference

### magic values
```
password: ELSILRACLIHP
game port: 17011
irc port: 6667
http port: 80 (team17) or 8081 (wormhole)
game timeout: 300 seconds (5 minutes)
max game name: 29 chars
```

### user flags format (realname field)
```
USER username host server :flags rank country version
USER HostingBuddy host server :51 11 ZZ 3.8.1
                               ↑  ↑  ↑  ↑
                               |  |  |  version
                               |  |  country code
                               |  rank (0-99?)
                               flags (hex, 2 digits)
```

### scheme codes
see worms2d.info/WormNET for full list
- Pf = party full
- Be = bazooka elite
- Intermediate = built-in scheme name
