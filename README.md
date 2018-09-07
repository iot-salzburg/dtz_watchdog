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
python3 cluster_watchdog/cluster_watchdog.py
```

View if the cluster is healthy in the [browser](http://il081:8081/).


### Meta Watchdog

Watchdog for the watchdog. If you are


### Restart when booting

