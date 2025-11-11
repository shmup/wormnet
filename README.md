## wormnet

minimal worms armageddon server - irc + http in one script

### quick start

```bash
./wormnet                 # run with defaults
./wormnet -c wormnet.toml # or with custom config
```

### setup

1. **copy the templates**
```bash
cp motd.template.txt motd.txt
cp news.template.html news.html
cp wormnet.template.toml wormnet.toml
```

2. **edit wormnet.toml**
```toml
[irc]
port = 6667
ip = ""  # auto-detects from connections (or set to override)
motd_file = "motd.txt"

[http]
port = 80  # internally 80, exposed as 8081 in docker
# connect_port = 6668  # if irc is port-forwarded to different external port
news_file = "news.html"

[channels.AnythingGoes]
scheme = "Pf,Be"
topic = "Anything goes!"
icon = 0
```

3. **run it**
```bash
./wormnet
./wormnet -c another-wormnet.toml
```

### configure worms

1. navigate to wherever worms is installed
2. go into `graphics/ServerLobby/`
3. edit either `ServerList.htm or `CommunityServerList.htm`
   (note: if community, check "use community server list" in game options)
4. add a link to your server: `<a href="http://localhost:8081">my wormnet</a>`

_for remote access, replace `localhost:8081` with your domain/ip_

_when editing these html files, you don't need to restart worms. just leave and
reenter wormnet_

### router setup (if hosting for others)

forward these ports to your server ip:
- **6667** - irc (tcp)
- **8081** (or 80) - http (tcp)

consider using dyndns/no-ip if you don't have a static ip

### docker

```bash
docker compose up -d   # build and run with docker in background
docker compose logs -f # view the logs
docker compose down    # stop and remove the container
```
