#!/usr/bin/env python3
import os
import sys
import json
import time
import socket
import logging
import requests
import slackweb
import pytz
from datetime import datetime
from redis import Redis
from flask import Flask, jsonify
from dotenv import load_dotenv
from multiprocessing import Process

__date__ = "03 July 2019"
__version__ = "1.4"
__email__ = "christoph.schranz@salzburgresearch.at"
__status__ = "Development"
__desc__ = """This program watches the state of each service, part of the DTZ system on the il07X cluster.
The following services will be watched:
- Zookeeper on il071, il072, il073
- Kafka on il071, il072, il073, il074, il075
- Swarm Services:
  - add-datastore_datastore-adapter
  - add-mqtt_adapter
  - add-opcua_adapter
  - dtz_master_controller_dtz_master_controller
  - elk_elasticsearch
  - grafana_grafana
  - elk_kibana
  - elk_logstash
  - gost_dashboard
  - gost_gost
  - gost_gost-db
  - hololens-adapter_adapter
  - mqtt_mqtt-broker
  - registry
  - visualizer_visualizer"""

# Configuration
STATUS_FILE = "status.log"
load_dotenv()
SLACK_URL = os.environ.get('SLACK_URL', "")
if SLACK_URL == "":
    print("No Slack URL found")
PORT = os.environ.get('PORT', "8081")
META_WATCHDOG_URL = os.environ.get('META_WATCHDOG_URL', "192.168.48.50")
SWARM_MAN_IP = os.environ.get('SWARM_MAN_IP', "192.168.48.71")
CLUSTER_WATCHDOG_HOSTNAME = os.environ.get('CLUSTER_WATCHDOG_HOSTNAME', "il071")

# Set timeouts
INTERVAL = 60  # check frequency
STARTUP_TIME = 10  # 120  # Wait timeout for other services
REACTION_TIME = 5 * 60  # Timeout in order to not notify when rebooting, or service scaling
NOTIFY_TIME = 60 * 60  # Time intervall for resending a notification

services = [
#    "zookeeper: 192.168.48.71:2181",
    "zookeeper: 192.168.48.72:2181",
    "zookeeper: 192.168.48.73:2181",
#    "kafka: 192.168.48.71:9092",
    "kafka: 192.168.48.72:9092",
    "kafka: 192.168.48.73:9092",
    "kafka: 192.168.48.74:9092",
    "kafka: 192.168.48.75:9092",
    "docker: add-datastore_datastore-adapter",
    "docker: add-mqtt_adapter",
    "docker: add-opcua_adapter",
    "docker: dtz_master_controller_dtz_master_controller",
    "docker: elk_elasticsearch",
    "docker: grafana_grafana",
    "docker: elk_kibana",
    "docker: elk_logstash",
    "docker: gost_dashboard",
    "docker: gost_gost",
    "docker: gost_gost-db",
    "docker: hololens-adapter_adapter",
    "docker: mqtt_mqtt-broker",
    "docker: registry",
    "docker: visualizer_visualizer",
    "meta watchdog"
]

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
        status = {"application": "dtz_cluster-watchdog",
                  "status": "FileNotFoundError"}
    return jsonify(status)


class Watchdog:
    def __init__(self):
        self.status = dict({"application": "dtz_cluster-watchdog",
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
                            "monitored_services": services})

        self.slack = slackweb.Slack(url=SLACK_URL)  # os.environ.get('SLACK_URL'))
        self.counter = None
        # If that fails, examine if the env variable is set correctly.
        with open(STATUS_FILE, "w") as f:
            f.write(json.dumps(self.status))

        print('Started Cluster watchdog. Status reachable at {}'.format("http://" + SWARM_MAN_IP + ":" + PORT))
        if socket.gethostname() == CLUSTER_WATCHDOG_HOSTNAME:  # If this is run by the host.
            self.slack.notify(text='Started Cluster watchdog. Status reachable at {}. Monitored services: {}'
                              .format("http://" + SWARM_MAN_IP + ":" + PORT, services))

    def start(self):
        """
        Runs periodically health-checks for each service and notifies via slack.
        :return:
        """
        time.sleep(STARTUP_TIME)  # Give the other services time when rebooting.

        self.status["status"] = "running"
        self.counter = NOTIFY_TIME
        # Set the status of each service to True
        self.service_status = {k.split(" ")[-1]: True for k in services}

        while True:
            status = list()
            status += self.check_kafka()
            status += self.check_docker_services()
            status += self.check_meta_watchdog()

            if status == list():
                self.status["cluster_status"] = "healthy"
                self.counter = NOTIFY_TIME
            else:
                self.status["cluster_status"] = status
                content = dict()
                content["status"] = status
                content["context"] = {"service runs at": "{}.{}".format(SWARM_MAN_IP, PORT),
                                      "monitored services": services}
                self.slack_notify(attachments=[
                    {'title': 'Datastack Warning',
                     'text': str(json.dumps(content, indent=4)), 'color': 'warning'}])
            self.status["last_check"] = datetime.utcnow().replace(tzinfo=pytz.UTC).replace(microsecond=0).isoformat()

            with open(STATUS_FILE, "w") as f:
                f.write(json.dumps(self.status))

            time.sleep(INTERVAL)

    def check_kafka(self):
        """
        Checks each zookeeper and kafka instance on the cluster
        :return: list of warnings if the same service is unavailable or not updated twice
        """
        status = list()
        # Check each service, zookeeper and kafka if it is available and gathers the same output
        avail_topics = "@init"
        for k, v in self.service_status.items():
            if "zookeeper: 192.168.48.7" in k:
                ret = os.popen("/kafka/bin/kafka-topics.sh --zookeeper {} --list".format(
                    k.split(" ")[-1])).readlines()
                if avail_topics == "@init":
                    avail_topics = ret
                if ret == "":
                    status.append({"service": k, "status": "no topics found"})
                else:
                    if avail_topics != ret:
                        if self.service_status[k] == True:
                            self.service_status[k] = False
                        else:
                            status.append({"service": k, "status": "topics don't match: {}".format(ret)})
            if "kafka: 192.168.48.7" in k:
                ret = os.popen("/kafka/bin/kafka-topics.sh --bootstrap-server {} --list".format(
                    k.split(" ")[-1])).readlines()
                if avail_topics == "@init":
                    avail_topics = ret
                if ret == "":
                    status.append({"service": k, "status": "no topics found"})
                else:
                    if avail_topics != ret:
                        if self.service_status[k] == True:
                            self.service_status[k] = False
                        else:
                            status.append({"service": k, "status": "topics don't match: {}".format(ret)})
        return status

    def check_docker_services(self):
        """
        Checks each docker service on the swarm manager (this node)
        :return: list of warnings if the same error occurs twice
        """
        status = list()
        # Check each service
        services = os.popen("docker service ls").readlines()
        print("Found {} docker services.".format(len(services)))

        for full_key, v in self.service_status.items():
            # Only extract services that start with docker:
            if not full_key.startswith("docker: "):
                continue
            k = full_key.replace("docker: ", "")
            found = False
            for service in services:
                # Service is available, check if it is replicated correctly
                if k == service.split()[1]:
                    reps = service.split()[3]
                    if (int(reps.split("/")[0]) != int(reps.split("/")[1])) or (int(reps.split("/")[0]) == 0):
                        if self.service_status[k] == True:
                            self.service_status[k] = False
                        else:
                            status.append({"service": k, "status": "replicas do not match or is 0: {}".format(service)})
                    found = True
            if not found:
                status.append({"service": k, "status": "service was not found in swarm"})
        return status

    def check_meta_watchdog(self):
        """
        Checks if the meta watchdog on META_WATCHDOG_URL is running
        :return: a warning is appended if the same error occurs twice
        """
        try:
            req = requests.get(url="http://{}:{}".format(META_WATCHDOG_URL, PORT))
            if req.status_code != 200:
                if self.service_status["meta_watchdog"] == True:
                    self.service_status["meta_watchdog"] = False
                else:
                    return [{"service": "meta watchdog",
                             "status": "Meta Watchdog at http://{}:{} is not reachable. More infos at {}.".format(
                                 META_WATCHDOG_URL, PORT, "http://" + SWARM_MAN_IP + ":" + PORT)}]
        except requests.exceptions.ConnectionError:
            if self.service_status["meta_watchdog"] == True:
                self.service_status["meta_watchdog"] = False
            else:
                return [{"service": "meta watchdog",
                         "status": "Meta Watchdog at http://{}:{} is not reachable. More infos at {}.".format(
                             META_WATCHDOG_URL, PORT, "http://" + SWARM_MAN_IP + ":" + PORT)}]
        return list()

    def slack_notify(self, attachments):
        """
        Sends notification to slack, but waits for REACTION_TIME and then sends only every NOTIFY_TIME
        :param attachments: message to send
        :return:
        """
        if self.counter >= NOTIFY_TIME + REACTION_TIME:
            # self.slack.notify(text="Testing messenger")
            if socket.gethostname() == CLUSTER_WATCHDOG_HOSTNAME:  # true on cluster node il071
                print("sending notification to slack")
                self.slack.notify(attachments=attachments)
            else:
                print(str(json.dumps({"Development mode, attachments": attachments}, indent=4, sort_keys=True)))
            self.counter = 0
        else:
            self.counter += INTERVAL
            print("Anomaly detected, but notify time of {} s not reached, increasing counter to {} s".format(
                NOTIFY_TIME + REACTION_TIME, self.counter))


if __name__ == '__main__':
    print("Starting cluster-watchdog, initializing.")

    # Starting Watchdog Process
    watchdog_instance = Watchdog()
    watchdog_routine = Process(target=Watchdog.start, args=(watchdog_instance,))
    watchdog_routine.start()

    # Starting webservice
    app.run(host="0.0.0.0", debug=False, port=PORT)
