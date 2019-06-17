#!/usr/bin/env python3
import os
import sys
import json
import time
import socket
import logging
import requests
import slackweb
from redis import Redis
from flask import Flask, jsonify
from dotenv import load_dotenv
from multiprocessing import Process

__date__ = "14 Juni 2019"
__version__ = "1.2"
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
  - elk_grafana
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
META_WATCHDOG_URL = os.environ.get('META_WATCHDOG_URL', "192.168.48.50")
SWARM_MAN_IP = os.environ.get('SWARM_MAN_IP', "192.168.48.71")
CLUSTER_WATCHDOG_HOSTNAME = os.environ.get('CLUSTER_WATCHDOG_HOSTNAME', "il071")
INTERVAL = 60  # in seconds, for checking
STARTUP_TIME = 10  # 120  # for other services
REACTION_TIME = 5 * 60  # Timeout in order to not notify when rebooting, or service scaling
NOTIFY_TIME = 60 * 60

services = [
    "zookeeper 192.168.48.71:2181",
    "zookeeper 192.168.48.72:2181",
    "zookeeper 192.168.48.73:2181",
    "kafka 192.168.48.71:9092",
    "kafka 192.168.48.72:9092",
    "kafka 192.168.48.73:9092",
    "kafka 192.168.48.74:9092",
    "kafka 192.168.48.75:9092",
    "add-datastore_datastore-adapter",
    "add-mqtt_adapter",
    "add-opcua_adapter",
    "dtz_master_controller_dtz_master_controller",
    "elk_elasticsearch",
    "elk_grafana",
    "elk_kibana",
    "elk_logstash",
    "gost_dashboard",
    "gost_gost",
    "gost_gost-db",
    "hololens-adapter_adapter",
    "mqtt_mqtt-broker",
    "registry",
    "visualizer_visualizer",

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
                  "status": "running"}
    return jsonify(status)


class Watchdog:
    def __init__(self):
        self.status = dict({"application": "dtz_cluster-watchdog",
                            "status": "initialisation",
                            "environment variables": {"SWARM_MAN_IP": SWARM_MAN_IP,
                                                      "META_WATCHDOG_URL": META_WATCHDOG_URL,
                                                      "SLACK_URL": SLACK_URL[:33] + "...",
                                                      "CLUSTER_WATCHDOG_HOSTNAME": CLUSTER_WATCHDOG_HOSTNAME},
                            "version": {"number": __version__,
                                        "build_date": __date__,
                                        "repository": "https://github.com/iot-salzburg/dtz-watchdog"},
                            "cluster status": None})

        self.slack = slackweb.Slack(url=SLACK_URL)  # os.environ.get('SLACK_URL'))
        # If that fails, examine if the env variable is set correctly.
        with open(STATUS_FILE, "w") as f:
            f.write(json.dumps(self.status))

        if socket.gethostname() == CLUSTER_WATCHDOG_HOSTNAME:  # If this is run by the host.
            self.slack.notify(text='Started Cluster watchdog on host {}'.format(socket.gethostname()))
            pass

    def start(self):
        """
        Runs periodically healthchecks for each service and notifies via slack.
        :return:
        """
        time.sleep(STARTUP_TIME)  # Give the other services time when rebooting.

        self.status["status"] = "running"
        c = NOTIFY_TIME
        self.service_status = {k: True for k in services}

        while True:
            status = list()
            status += self.check_kafka()
            status += self.check_docker_services()
            status += self.check_meta_watchdog()

            if status == list():
                self.status["cluster status"] = "healthy"
                c = NOTIFY_TIME
            else:
                self.status["cluster status"] = status
                c = self.slack_notify(c, attachments=[
                    {'title': 'Datastack Warning', 'text': str(json.dumps(status, indent=4)), 'color': 'warning'}])
                #c = self.slack_notify(c,
                #                  attachments=[{'title': 'Datastack Warning', 'text': str(status), 'color': 'warning'}])
            with open(STATUS_FILE, "w") as f:
                f.write(json.dumps(self.status))

            time.sleep(INTERVAL)

    def check_kafka(self):
        status = list()
        # Check each service, zookeeper and kafka if it is available and gathers the same output
        # Send notif only when the service is not reachable twice
        # services = ["stack_elasticsearch", "stack_logstash", "stack_kibana", "stack_grafana", "stack_jupyter"]
        avail_topics = "@init"
        for k, v in self.service_status.items():
            if "zookeeper 192.168.48.7" in k:
                ret = os.popen("/kafka/bin/kafka-topics.sh --{} --list".format(
                    k)).readlines()
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
            if "kafka 192.168.48.7" in k:
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
        status = list()
        # Check each service
        print("checking docker")
        services = os.popen("docker service ls").readlines()
        print("Found docker services:")
        for service in services:
            print(service)

        for k, v in self.service_status.items():
            if "zookeeper 192.168.48.7" in k or "kafka 192.168.48.7" in k or k == "meta watchdog":
                continue

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
        # Check connection:
        try:
            req = requests.get(url="http://{}:8081".format(META_WATCHDOG_URL))
            if req.status_code != 200:
                if self.service_status["meta watchdog"] == True:
                    self.service_status["meta watchdog"] = False
                else:
                    return [{"service": "meta watchdog",
                             "status": "Service on {}:8081 not reachable".format(META_WATCHDOG_URL)}]
        except requests.exceptions.ConnectionError:
            if self.service_status["meta watchdog"] == True:
                self.service_status["meta watchdog"] = False
            else:
                return [{"service": "meta watchdog",
                         "status": "Service on {}:8081 not reachable".format(META_WATCHDOG_URL)}]
        return list()

    def slack_notify(self, counter, attachments):
        if counter >= NOTIFY_TIME + REACTION_TIME:
            # self.slack.notify(text="Testing messenger")
            if socket.gethostname() == CLUSTER_WATCHDOG_HOSTNAME:  # true on cluster node il071
                print("sending notification to slack")
                self.slack.notify(attachments=attachments)
            else:
                print(str(json.dumps({"Development mode, attachments": attachments}, indent=4, sort_keys=True)))
            counter = 0
        else:
            counter += INTERVAL
            print("Anomaly detected, but notify time of {} s not reached, increasing counter to {} s".format(NOTIFY_TIME + REACTION_TIME, counter))
        return counter


if __name__ == '__main__':
    print("Starting cluster-watchdog, initial waiting for some time")
    watchdog_instance = Watchdog()
    watchdog_routine = Process(target=Watchdog.start, args=(watchdog_instance,))
    watchdog_routine.start()

    app.run(host="0.0.0.0", debug=False, port=8081)
