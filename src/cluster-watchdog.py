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
__version__ = "1.2"
__email__ = "christoph.schranz@salzburgresearch.at"
__status__ = "Development"
__desc__ = """This program watches the state of each service, part of the DTZ system on the il08X cluster."""

# Configuration
STATUS_FILE = "status.log"
SLACK_URL = os.environ.get('SLACK_URL')
META_WATCHDOG_URL = os.environ.get('META_WATCHDOG_URL', "192.168.48.50")
SWARM_MAN_IP = os.environ.get('SWARM_MAN_IP', "192.168.48.81")
INTERVAL = 60  # in seconds
STARTUP_TIME = 120  # for other services
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
        status = {"application": "dtz_cluster-watchdog",
                  "status": "FileNotFoundError"}
    return jsonify(status)


class Watchdog:
    def __init__(self):
        self.status = dict({"application": "dtz_cluster-watchdog",
                            "status": "initialisation",
                            "environment variables": {"SWARM_MAN_IP": SWARM_MAN_IP, "META_WATCHDOG_URL": META_WATCHDOG_URL,
                                                      "SLACK_URL": SLACK_URL[:33]+"..."},
                            "version": {"number": __version__, "build_date": __date__,
                                        "repository": "https://github.com/iot-salzburg/dtz-watchdog"},
                            "cluster status": None})
        self.slack = slackweb.Slack(url=SLACK_URL)  # os.environ.get('SLACK_URL'))
        # If that fails, examine if the env variable is set correctly.
        with open(STATUS_FILE, "w") as f:
            f.write(json.dumps(self.status))
        # print(os.environ.get('SLACK_URL'))

        if socket.gethostname().startswith(SWARM_MAN_IP[:4]):  # If this is run by the host.
            self.slack.notify(text='Started Cluster watchdog on host {}'.format(socket.gethostname()))

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
            status += self.check_kafka()
            status += self.check_datastack()
            status += self.check_sensorthings()
            status += self.check_operator_dashboard()
            status += self.check_mqtt_broker()
            status += self.check_mqtt_adapter()
            status += self.check_db_adapter()
            # status += self.check_opc_adapter() TODO implement if opc adapter stands
            status += self.check_meta_watchdog()

            if status == list():
                self.status["cluster status"] = "healthy"
                c = NOTIFY_TIME
            else:
                self.status["cluster status"] = status
                c = self.slack_notify(c, attachments=[{'title': 'Datastack Warning', 'text': str(json.dumps(status, indent=4)), 'color': 'warning'}])
                #c = self.slack_notify(c, attachments=[{'title': 'Datastack Warning', 'text': str(status), 'color': 'warning'}])
            with open(STATUS_FILE, "w") as f:
                f.write(json.dumps(self.status))
            time.sleep(INTERVAL)

    def check_kafka(self):
        status = list()
        # Check each service
        # services = ["stack_elasticsearch", "stack_logstash", "stack_kibana", "stack_grafana", "stack_jupyter"]
        services = os.popen("/kafka/bin/kafka-topics.sh --zookeeper {}:2181 --list".format(SWARM_MAN_IP)).readlines()
        if "dtz.logging\n" not in services:
            status.append({"service": "kafka", "status": "Topic 'dtz.logging' not found"})
        if "dtz.sensorthings\n" not in services:
            status.append({"service": "kafka", "status": "Topic 'dtz.sensorthings' not found"})
        return status

    def check_datastack(self):
        status = list()
        # Check each service
        # services = ["stack_elasticsearch", "stack_logstash", "stack_kibana", "stack_grafana", "stack_jupyter"]
        services = os.popen("docker service ls | grep stack_").readlines()
        if len(services) != 5:
            status.append({"service": "datastack", "status": "Number of services is not 5.", "services": services})
        for service in services:
            fields = [s for s in service.split(" ") if s != ""]
            id_ser = fields[0]
            name = fields[1]
            replicas = fields[3]
            image = fields[4]
            rep1, rep2 = replicas.split("/")
            if rep1 != rep2:
                status.append({"service": name, "ID": id_ser, "REPLICAS": replicas,
                               "IMAGE": image})
        return status

    def check_sensorthings(self):
        status = list()
        # Check each service
        services = os.popen("docker service ls | grep st_").readlines()
        if len(services) != 3:
            status.append({"service": "sensorthings", "status": "Number of services is not 3.", "services": services})
        for service in services:
            fields = [s for s in service.split(" ") if s != ""]
            id_ser = fields[0]
            name = fields[1]
            replicas = fields[3]
            image = fields[4]
            rep1, rep2 = replicas.split("/")
            if rep1 != rep2:
                status.append({"service": name, "ID": id_ser, "REPLICAS": replicas,
                               "IMAGE": image})
        # Check connection:
        try:
            req = requests.get(url="http://{}:8084/v1.0/Things".format(SWARM_MAN_IP))
            if req.status_code != 200:
                status.append({"service": "sensorthings", "status": "Service on port 8084 not reachable"})
            if "value" not in req.json().keys():
                status.append({"service": "sensorthings", "status": "No content found in http://{}:8084/v1.0/Things"})
        except requests.exceptions.ConnectionError:
            status.append({"service": "sensorthings", "status": "Connection refused"})
        return status

    def check_operator_dashboard(self):
        status = list()
        # Check each service
        services = os.popen("docker service ls | grep op_").readlines()
        if len(services) != 2:
            status.append({"service": "operator dashboard", "status": "Number of services is not 2.", "services": services})
        for service in services:
            fields = [s for s in service.split(" ") if s != ""]
            id_ser = fields[0]
            name = fields[1]
            replicas = fields[3]
            image = fields[4]
            rep1, rep2 = replicas.split("/")
            if rep1 != rep2:
                status.append({"service": name, "ID": id_ser, "REPLICAS": replicas,
                               "IMAGE": image})
        # Check connection:
        try:
            req = requests.get(url="http://{}:6789".format(SWARM_MAN_IP))
            if req.status_code != 200:
                status.append({"service": "operator dashboard", "status": "Service on port 6789 not reachable"})
        except requests.exceptions.ConnectionError:
            status.append({"service": "operator dashboard", "status": "Service on port 6789, connection refused"})
        return status

    def check_mqtt_broker(self):
        status = list()
        # Check each service
        services = os.popen("docker service ls | grep mqtt_mqtt-broker").readlines()
        if len(services) != 1:
            status.append({"service": "mqtt broker", "status": "Number of services is not 1.", "services": services})
        for service in services:
            fields = [s for s in service.split(" ") if s != ""]
            id_ser = fields[0]
            name = fields[1]
            replicas = fields[3]
            image = fields[4]
            rep1, rep2 = replicas.split("/")
            if rep1 != rep2:
                status.append({"service": name, "ID": id_ser, "REPLICAS": replicas,
                               "IMAGE": image})
        return status

    def check_mqtt_adapter(self):
        status = list()
        # Check each service
        services = os.popen("docker service ls | grep add-mqtt_").readlines()
        if len(services) != 1:
            status.append({"service": "mqtt adapter", "status": "Number of services is not 1.", "services": services})
        for service in services:
            fields = [s for s in service.split(" ") if s != ""]
            id_ser = fields[0]
            name = fields[1]
            replicas = fields[3]
            image = fields[4]
            rep1, rep2 = replicas.split("/")
            if rep1 != rep2:
                status.append({"service": name, "ID": id_ser, "REPLICAS": replicas,
                               "IMAGE": image})
        return status

    def check_db_adapter(self):
        status = list()
        # Check each service
        services = os.popen("docker service ls | grep db-adapter_").readlines()
        if len(services) != 2:
            status.append({"service": "db adapter", "status": "Number of services is not 2.", "services": services})
        for service in services:
            fields = [s for s in service.split(" ") if s != ""]
            id_ser = fields[0]
            name = fields[1]
            replicas = fields[3]
            image = fields[4]
            rep1, rep2 = replicas.split("/")
            if rep1 != rep2:
                status.append({"service": name, "ID": id_ser, "REPLICAS": replicas,
                               "IMAGE": image})
        # Check connection:
        try:
            req = requests.get(url="http://{}:3030".format(SWARM_MAN_IP))
            if req.status_code != 200:
                status.append({"service": "db-adapter status", "status": "Service on port 3030 not reachable"})
            elif req.json()["status"] != "running":
                status.append({"service": "db-adapter status", "status": req.json()["status"]})
        except requests.exceptions.ConnectionError:
            status.append({"service": "db-adapter status", "status": "Connection refused"})
        return status

    def check_meta_watchdog(self):
        # Check connection:
        try:
            req = requests.get(url="http://{}:8081".format(META_WATCHDOG_URL))
            if req.status_code != 200:
                return [{"service": "meta watchdog", "status": "Service on {}:8081 not reachable".format(META_WATCHDOG_URL)}]
        except requests.exceptions.ConnectionError:
            return [
                {"service": "meta watchdog", "status": "Service on {}:8081 not reachable".format(META_WATCHDOG_URL)}]
        return list()


    def slack_notify(self, counter, attachments):
        if counter >= NOTIFY_TIME + REACTION_TIME:
            # self.slack.notify(text="Testing messenger")
            if socket.gethostname().startswith(SWARM_MAN_IP[:4]):  # true on cluster node il081
                self.slack.notify(attachments=attachments)
            else:
                print(str(json.dumps({"Development mode, attachments": attachments}, indent=4, sort_keys=True)))
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
