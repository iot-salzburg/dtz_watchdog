FROM python:3.6
# not using onbuild, because changed code results in installation time

MAINTAINER Christoph Schranz <christoph.schranz@salzburgresearch.at>

# test internet connection and dns settings. If apt-get update fails, restart
# docker service, check internet connection and dns settings in /etc/docker/daemon.json
# RUN apt-get update

RUN apt-get update && apt-get install openjdk-8-jre wget -y && \
    export kafka_version=2.2.0 && \
    wget https://archive.apache.org/dist/kafka/${kafka_version}/kafka_2.12-${kafka_version}.tgz && \
    tar -xvzf kafka_2.12-${kafka_version}.tgz && \
    rm kafka_2.12-${kafka_version}.tgz && \
    rm -R /kafka > /dev/null 2>&1 || true && \
    mv kafka_2.12-${kafka_version} /kafka && \
    chmod +x /kafka/bin/*

# install the official librdkafka client written in C
ENV LIBRDKAFKA_VERSION 0.11.1
RUN apt-get update && \
    git clone https://github.com/edenhill/librdkafka && cd librdkafka && \
    git checkout v${LIBRDKAFKA_VERSION} && \
    ./configure && make && make install && ldconfig

# install confluent-kafka-client
ENV CONFLUENT_KAFKA_VERSION 0.11.5
RUN pip install confluent-kafka==${CONFLUENT_KAFKA_VERSION}


# Copy the content of this folder into the hosts home directory.
ADD requirements.txt .
RUN pip install -r requirements.txt

RUN mkdir /src
ADD . /src

# setup proper configuration
ENV PYTHONPATH /
WORKDIR /src

ENTRYPOINT ["python", "/src/cluster-watchdog.py"]
