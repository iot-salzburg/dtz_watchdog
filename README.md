# Watchdog

The watchdog monitors each service on the dtz cluster and notifies
via Slack. Additionally, a second watchdog watches the main one.


## Contents

1. [Requirements](#requirements)
2. [Usage](#usage)



## Requirements

Clone the repository and set the environment:

```bash
git clone https://github.com/iot-salzburg/dtz_watchdog.git
cd dtz_watchdog
virtualenv -p $(which python3) setup/venv
source setup/venv/bin/activate
python -m pip install -r requirements.txt
```

## Usage

### Cluster Watchdog

The Watchdog uses a slack webhook to notify about cluster issues. Therefore open in Slack a new channel, then `add app`,
look for `Incoming WebHooks`, `Add Configuration` and select the desired Slack Channel. Then a new configuration will
show the WebHook-Url in the form: `https://hooks.slack.com/services/id1/id2/id3`. This URL should be set as
environment variable on the host. Note that the **url is in quotes**, so that
it can be accessed better within python. Additionally set the ip-address and hostname of the cluster watchdog, and also the ip-address of the meta watchdog.

```bash
echo "SLACK_URL=https://hooks.slack.com/services/id1/id2/id3" >> .env
echo "CLUSTER_WATCHDOG_HOSTNAME=il071" >> .env
echo "SWARM_MAN_IP=192.168.48.71" >> .env
echo "META_WATCHDOG_URL=192.168.48.50" >> .env
echo "PORT=8081" >> .env
cat .env
```

Now, the Watchdogs can be started.

```bash
user@il071:dtz_watchdog$ python3 src/cluster-watchdog.py
user@il050:dtz_watchdog$ python3 src/meta-watchdog.py
```


View if the cluster is healthy [http://il071:8081/](http://192.168.48.71:8081/).


### Deployment

Adjust the settings and copy the systemd service:
```
sudo nano setup/watchdog.service
sudo cp setup/watchdog.service /etc/systemd/system/watchdog.service
```

An execute to enable:
```
sudo systemctl enable watchdog.service
sudo systemctl start watchdog
sudo systemctl status watchdog
```


### Meta Watchdog Deployment

As there would be no notifications if the host server itself crashes,
we deploy a meta watchdog, that watches only on the cluster watchdog.

Therefore, Select on another host:

Create a service with `systemd`:
```
sudo nano /etc/systemd/system/meta-watchdog.service
```
With the content:
```
[Unit]
Description=Autostart DTZ Meta Watchdog
After=network.target

[Service]
User=iotdev
Group=iotdev
Environment=SLACK_URL=https://hooks.slack.com/services/id1/id2/id3
Environment=SWARM_MAN_IP=192.168.48.71
Environment=META_WATCHDOG_URL=192.168.48.50
WorkingDirectory=/srv/dtz_watchdog/
ExecStart=/srv/dtz_watchdog/src/meta-watchdog.py
ExecReload=/bin/kill -HUP $MAINPID

[Install]
WantedBy=multi-user.target
```
An run to enable:
```
sudo systemctl enable meta-watchdog.service
sudo systemctl start meta-watchdog
sudo systemctl status meta-watchdog
```
