#!/usr/bin/env python3
import os
import sys
import json
import time
import socket
import requests
import slackweb
from redis import Redis
from flask import Flask, jsonify
from multiprocessing import Process


__date__ = "12 September 2018"
__version__ = "1.1"
__email__ = "christoph.schranz@salzburgresearch.at"
__status__ = "Development"
__desc__ = """This program watches the state of the cluster-watchdog, part of the DTZ system on the il08X cluster."""


STATUS_FILE = "meta_status.log"
SLACK_URL =  os.environ.get('SLACK_URL')

# Configuration:
# print(os.environ.get('SWARM_MAN_IP'))
SWARM_MAN_IP = os.environ.get('SWARM_MAN_IP', "192.168.48.81")
INTERVAL = 20  # in seconds
STARTUP_TIME = 0  # for other services
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
                            "environment variables": {"SWARM_MAN_IP": SWARM_MAN_IP, "SLACK_URL": SLACK_URL[:33]+"..."},
                            "version": {"number": __version__, "build_date": __date__,
                                        "repository": "https://github.com/iot-salzburg/dtz-watchdog"},
                            "cluster status": None})
        self.slack = slackweb.Slack(url=SLACK_URL)  # os.environ.get('SLACK_URL'))
        # If that fails, examine if the env variable is set correctly.
        with open(STATUS_FILE, "w") as f:
            f.write(json.dumps(self.status))
        # print(os.environ.get('SLACK_URL'))
        self.slack.notify(text='Started meta-watchdog on host {}'.format(socket.gethostname()))

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
                self.status["cluster status"] = "healthy"
                c = NOTIFY_TIME
            else:
                self.status["cluster status"] = status
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
                return [{"service": "cluster watchdog", "status": "Service on port 8081 not reachable"}]
        except requests.exceptions.ConnectionError:
            return [{"service": "cluster watchdog", "status": "Service on port 8081 not reachable"}]
        return list()

    def slack_notify(self, counter, attachments):
        if counter >= NOTIFY_TIME:
            # self.slack.notify(text="Testing messenger")
            print(str(json.dumps({"Development mode, attachments": attachments}, indent=4, sort_keys=True)))
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
