# Watchdog

The watchdog monitors each service on the dtz cluster and notifies
via Slack. Additionally, a second watchdog watches the main one.


## Contents

1. [Requirements](#requirements)
2. [Usage](#usage)



## Requirements

```bash
git clone https://github.com/iot-salzburg/dtz_watchdog.git
cd dtz-watchdog/
pip3 install -r requirements.txt
```



## Usage

### Cluster Watchdog

The Watchdog uses a slack webhook to notify about cluster issues. Therefore open in Slack a new channel, then `add app`,
look for `Incoming WebHooks`, `Add Configuration` and select the desired Slack Channel. Then a new configuration will
show the WebHook-Url in the form: `https://hooks.slack.com/services/id1/id2/id3`. This URL should be set as
environment variable on the host.

```bash
export SLACK_URL=https://hooks.slack.com/services/id1/id2/id3
echo $SLACK_URL
```

Now, the Watchdog can be started.

```bash
python3 src/cluster_watchdog.py
```

View if the cluster is healthy in the [browser](http://il081:8081/).



### Deployment

Create a service with `systemd`:
```
sudo nano /etc/systemd/system/cluster-watchdog.service
```
With the content:
```
[Unit]
Description=Autostart DTZ Watchdog
After=network.target

[Service]
User=iotdev
Group=iotdev
Environment=SLACK_URL=https://hooks.slack.com/services/id1/id2/id3
WorkingDirectory=/srv/dtz_watchdog/
ExecStart=/srv/dtz_watchdog/src/cluster-watchdog.py
ExecReload=/bin/kill -HUP $MAINPID

[Install]
WantedBy=multi-user.target
```
An run to enable:
```
sudo systemctl enable cluster-watchdog.service
sudo systemctl start cluster-watchdog.service
sudo systemctl status cluster-watchdog.service
```

