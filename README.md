# Watchdog

The watchdog monitors each service on the dtz cluster and notifies
via Slack. Additionally, a second watchdog watches the main one.


## Contents

1. [Requirements](#requirements)
2. [Usage](#usage)
3. [Configuration](#configuration)
4. [Trouble-Shooting](#Trouble-shooting)

## Requirements

```bash
git clone https://github.com/iot-salzburg/dtz_watchdog.git
cd dtz-watchdog/
pip3 install -r requirements.txt
```

## Usage

### Cluster Watchdog
```bash
python3 src/cluster_watchdog.py
```

View if the cluster is healthy in the [browser](http://il081:8081/).


### Meta Watchdog

Watchdog for the watchdog. If you are

/srv/dtz_watchdog/cluster_watchdog


### Start when booting

Add both scripts to the autostart script `~/.bashrc`:
```
python3 /path/to/dtz-watchdog/src/cluster_watchdog.py
python3 /path/to/dtz-watchdog/src/meta_watchdog.py
```
