#!/usr/bin/env python3
import os
import sys
import json
import time
import socket
import requests
import slackweb
import pytz
from datetime import datetime
from redis import Redis
from flask import Flask, jsonify
from dotenv import load_dotenv
from multiprocessing import Process


__date__ = "10 January 2020"
__version__ = "1.4"
__email__ = "christoph.schranz@salzburgresearch.at"
__status__ = "Development"
__desc__ = """This program watches the state of the cluster-watchdog, part of the DTZ system on the il07X cluster."""


# Configuration:
STATUS_FILE = "meta_status.log"
load_dotenv()
SLACK_URL = os.environ.get('SLACK_URL', "")
if SLACK_URL == "":
    print("No Slack URL found")
PORT = os.environ.get('PORT', "8081")
META_WATCHDOG_URL = os.environ.get('META_WATCHDOG_URL', "192.168.48.50")
SWARM_MAN_IP = os.environ.get('SWARM_MAN_IP', "192.168.48.72")
CLUSTER_WATCHDOG_HOSTNAME = os.environ.get('CLUSTER_WATCHDOG_HOSTNAME', "il072")

# Set timeouts
INTERVAL = 20  # in seconds
STARTUP_TIME = 0  # for other services
REACTION_TIME = 2*60  # Timeout in order to not notify when rebooting
NOTIFY_TIME = 60*60

# webservice setup
app = Flask(__name__)
redis = Redis(host='redis', port=6379)


@app.route('/')
def print_cluster_status():
    """
    This function is called by a webserver request and prints the current cluster state
    :return:
    """
    try:
        with open(STATUS_FILE) as f:
            status = json.loads(f.read())
    except FileNotFoundError:
        status = {"application": "dtz_meta-watchdog",
                  "status": "init"}
    return jsonify(status)


class Watchdog:
    def __init__(self):
        self.status = dict({"application": "dtz_meta-watchdog",
                            "status": "initialisation",
                            "environment_variables": {"cluster_watchdog_url": "http://" + SWARM_MAN_IP + ":" + PORT,
                                                      "meta_watchdog_url": "http://" + META_WATCHDOG_URL + ":" + PORT,
                                                      "SLACK_URL": SLACK_URL[:33] + "...",
                                                      "cluster_watchdog_hostname": CLUSTER_WATCHDOG_HOSTNAME},
                            "version": {"number": __version__,
                                        "build_date": __date__,
                                        "status": "initialisation",
                                        "last_init": datetime.utcnow().replace(tzinfo=pytz.UTC).replace(microsecond=0).isoformat(),
                                        "repository": "https://github.com/iot-salzburg/dtz_watchdog"},
                            "cluster_status": None,
                            "monitored_services": "cluster-watchdog"})
        self.slack = slackweb.Slack(url=SLACK_URL)  # os.environ.get('SLACK_URL'))
        # If that fails, examine if the env variable is set correctly.
        with open(STATUS_FILE, "w") as f:
            f.write(json.dumps(self.status))
        # print(os.environ.get('SLACK_URL'))
        self.slack.notify(text='Started meta-watchdog on {}, infos available at {}'.format(
            META_WATCHDOG_URL, "http://" + META_WATCHDOG_URL + ":" + PORT))

    def start(self):
        """
        Runs periodically healthchecks for each service and notifies via slack.
        :return:
        """
        time.sleep(STARTUP_TIME)  # Give the other services time when rebooting.

        self.status["status"] = "running"
        c = NOTIFY_TIME
        while True:
            status = list()
            status = self.check_cluster_watchdog()

            if status == list():
                self.status["cluster_status"] = "healthy"
                c = NOTIFY_TIME
            else:
                self.status["cluster_status"] = status
                c = self.slack_notify(c, attachments=[{'title': 'Meta-Watchdog Warning',
                                                       'text': str(json.dumps(status, indent=4)),
                                                       'color': 'warning'}])
            with open(STATUS_FILE, "w") as f:
                f.write(json.dumps(self.status))
            time.sleep(INTERVAL)

    def check_cluster_watchdog(self):
        # Check connection:
        try:
            req = requests.get(url="http://{}:8081".format(SWARM_MAN_IP))
            if req.status_code != 200:
                return [{"service": "cluster watchdog",
                         "status": "Cluster Watchdog at http://{}:{} is not reachable. More infos at {}.".format(
                             SWARM_MAN_IP, PORT, "http://" + META_WATCHDOG_URL + ":" + PORT)}]
        except requests.exceptions.ConnectionError:
            return [{"service": "cluster watchdog",
                     "status": "Cluster Watchdog at http://{}:{} is not reachable. More infos at {}.".format(
                         SWARM_MAN_IP, PORT, "http://" + META_WATCHDOG_URL + ":" + PORT)}]
        return list()

    def slack_notify(self, counter, attachments):
        if counter >= NOTIFY_TIME + REACTION_TIME:
            # self.slack.notify(text="Testing messenger")
            self.slack.notify(attachments=attachments)
            counter = 0
        else:
            counter += INTERVAL
        return counter


if __name__ == '__main__':
    print("Starting cluster-watchdog, initial waiting for some time")
    # start kafka to logstash streaming in a subprocess
    watchdog_instance = Watchdog()
    watchdog_routine = Process(target=Watchdog.start, args=(watchdog_instance,))
    watchdog_routine.start()

    app.run(host="0.0.0.0", debug=False, port=8081)
