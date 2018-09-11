#!//usr/bin/env python3

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
# from logstash import TCPLogstashHandler


__date__ = "07 September 2018"
__version__ = "1.0"
__email__ = "christoph.schranz@salzburgresearch.at"
__status__ = "Development"
__desc__ = """This program watches the state of each service, part of the DTZ system on the il08X cluster."""


STATUS_FILE = "status.log"
# META_WATCHDOG_URL =

# Configuration:
SWARM_MAN_IP = "192.168.48.81"
INTERVAL = 60  # in seconds
STARTUP_TIME = 0 #120
NOTIFY_TIME=10*60


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
        status = {"application": "db-adapter",
                  "status": "running"}
    return jsonify(status)


class Watchdog:
    def __init__(self):
        self.status = dict({"application": "db-adapter",
                            "status": "initialisation",
                            "version": {"number": __version__, "build_date": __date__,
                                        "repository": "https://github.com/iot-salzburg/dtz-watchdog"},
                            "cluster status": None})

    def start(self):
        """
        Runs periodically healthchecks for each service and notifies via slack.
        :return:
        """
        self.slack = slackweb.Slack(url=os.getenv('SLACK_URL'))
        if socket.gethostname().startswith("il08"):
            self.slack.notify(text='Started Cluster watchdog on host {}'.format(socket.gethostname()))

        self.status["status"] = "running"
        print("Started cluster watchdog")
        c = NOTIFY_TIME
        while True:
            status = list()
            status += self.check_kafka()
            status += self.check_datastack()
            status += self.check_sensorthings()
            status += self.check_operator_dashboard()
            status += self.check_mqtt_broker()
            status += self.check_mqtt_adapter()
            # status += self.check_opc_adapter() TODO implement if opc adapter stands
            # status += self.check_meta_watchdog() TODO deploy meta-watchdog and watch it too

            if status == list():
                self.status["cluster status"] = "healthy"
                c = NOTIFY_TIME
            else:
                self.status["cluster status"] = status
                c = self.slack_notify(c, attachments=[{'title': 'Datastack Warning', 'text': status, 'color': 'warning'}])
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
        req = requests.get(url="http://{}:8084".format(SWARM_MAN_IP))
        if req.status_code != 200:
            status.append({"service": "sensorthings", "status": "Service on port 8084 not reachable"})

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
        req = requests.get(url="http://{}:6789".format(SWARM_MAN_IP))
        if req.status_code != 200:
            status.append({"service": "operator dashboard", "status": "Service on port 6789 not reachable"})
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
        req = requests.get(url="http://{}:3030".format(SWARM_MAN_IP))
        if req.status_code != 200:
            status.append({"service": "db-adapter status", "status": "Service on port 3030 not reachable"})
        elif req.json()["status"] != "running":
            status.append({"service": "db-adapter status", "status": req.json()["status"]})
        return status

    def slack_notify(self,counter, attachments):
        if counter >= NOTIFY_TIME:
            if socket.gethostname().startswith("il08"):  # true on cluster node il081
                self.slack.notify(attachments=json.dumps({"attachments": attachments}, indent=4, sort_keys=True))
            else:
                print(str(json.dumps({"Development mode, attachments": attachments}, indent=4, sort_keys=True)))
            counter = 0
        else:
            counter += INTERVAL
        return counter


if __name__ == '__main__':
    print("Starting cluster-watchdog, initial waiting for some time")
    time.sleep(STARTUP_TIME)  # Give the other services time when rebooting.
    # start kafka to logstash streaming in a subprocess
    watchdog_instance = Watchdog()
    watchdog_routine = Process(target=Watchdog.start, args=(watchdog_instance,))
    watchdog_routine.start()

    app.run(host="0.0.0.0", debug=False, port=8081)
