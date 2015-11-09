#!/bin/bash

HOST_IP=localhost

function infra_start {

    docker run -d \
       --name kolla_zookeeper \
       -p 2181:2181 \
       -p 2888:2888 \
       -p 3888:3888 \
       garland/zookeeper

    docker run --net="host" \
       --name kolla_mesos_master \
       -p 5050:5050 \
       -e "MESOS_HOSTNAME=${HOST_IP}" \
       -e "MESOS_IP=${HOST_IP}" \
       -e "MESOS_ZK=zk://${HOST_IP}:2181/mesos" \
       -e "MESOS_PORT=5050" \
       -e "MESOS_LOG_DIR=/var/log/mesos" \
       -e "MESOS_QUORUM=1" \
       -e "MESOS_REGISTRY=in_memory" \
       -e "MESOS_WORK_DIR=/var/lib/mesos" \
       -d \
       garland/mesosphere-docker-mesos-master

    docker run \
       -d \
       -p 8080:8080 \
       garland/mesosphere-docker-marathon --master zk://${HOST_IP}:2181/mesos \
       --zk zk://${HOST_IP}:2181/marathon

    docker run -d \
       --name kolla_mesos_slave_1 \
       --entrypoint="mesos-slave" \
       -e "MESOS_MASTER=zk://${HOST_IP}:2181/mesos" \
       -e "MESOS_LOG_DIR=/var/log/mesos" \
       -e "MESOS_LOGGING_LEVEL=INFO" \
       garland/mesosphere-docker-mesos-master:latest

    echo "Mesos    > http://${HOST_IP}:5050"
    echo "Marathon > http://${HOST_IP}:8080"
}

function infra_stop {
    docker rm -f $(docker ps -a -q --filter="name=kolla")
}

function usage {
    cat <<EOF
Usage: $0 COMMAND [options]

Options:
    --host, -i <host_ip> Specify path to host ip
    --help, -h                       Show this usage information

Commands:
    start  Start required infrastructure
    stop  Stop required infrastructure
EOF
}

ARGS=$(getopt -o hi: -l help,host: --name "$0" -- "$@") || { usage >&2; exit 2; }
eval set -- "$ARGS"

while [ "$#" -gt 0 ]; do
    case "$1" in
        (--host|-i)
            HOST_IP="$2"
            shift 2
            ;;

        (--help|-h)
            usage
            shift
            exit 0
            ;;

        (--)
            shift
            break
            ;;

        (*)
            echo "error"
            exit 3
            ;;
    esac
done

case "$1" in
(start)
    infra_start
    ;;

(stop)
    infra_stop
    ;;

(*)
    usage
    exit 0
    ;;
esac
