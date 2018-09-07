import os
import sys
import json
import time
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

# Configuration:
CLUSTER_IP = "192.168.48.81"
INTERVALL = 5 #* 60  # in seconds

# webservice setup
app = Flask(__name__)
redis = Redis(host='redis', port=6379)


@app.route('/')
def print_cluster_status():
    """
    This function is called by a sebserver request and prints the current meta information.
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
        self.status["status"] = "running"
        while True:
            status = list()
            status += self.check_datastack()
            # status.append(check_sensorthings())
            # status.append(check_kafka())
            # status.append(check_operator_dashboard())
            # status.append(check_mqtt_broker())
            # status.append(check_mqtt_adapter())
            # status.append(check_opc_adapter())
            print(status)

            if status == list():
                self.status["cluster status"] = "healthy"
            else:
                self.status["cluster status"] = status
            with open(STATUS_FILE, "w") as f:
                f.write(json.dumps(self.status))
                print(status)
            time.sleep(INTERVALL)


    def check_datastack(self):
        status = list()
        # Check each service
        # services = ["stack_elasticsearch", "stack_logstash", "stack_kibana", "stack_grafana", "stack_jupyter"]
        services = os.popen("docker service ls | grep stack_").readlines()
        if len(services) != 5:
            status.append({"service": "datastack", "status": "Number of services is not 5."})
        for service in services:
            fields = [s for s in service.split(" ") if s != ""]
            print(fields)
            id_ser = fields[0]
            name = fields[1]
            replicas = fields[3]
            image = fields[4]
            print(replicas.split("/"))
            rep1, rep2 = replicas.split("/")
            if rep1 != rep2:
                status.append({"service": name, "ID": id_ser, "REPLICAS": replicas,
                               "IMAGE": image})
        print(status)
        return status


if __name__ == '__main__':
    # start kafka to logstash streaming in a subprocess
    watchdog_instance = Watchdog()
    watchdog_routine = Process(target=Watchdog.start, args=(watchdog_instance,))
    watchdog_routine.start()

    app.run(host="0.0.0.0", debug=False, port=8081)
