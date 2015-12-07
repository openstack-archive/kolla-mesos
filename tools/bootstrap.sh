#!/bin/bash

NET_IFACE=eth2

function get_host_ip {
    echo $(ip addr show $NET_IFACE | grep -Po 'inet \K[\d.]+')
}

HOST_IP=$(get_host_ip)

function infra_start {
    docker run -d \
        --net host \
        --name kolla_zookeeper \
        --restart always \
        mesoscloud/zookeeper

    docker run -d \
        --net host \
        --name kolla_mesos_master \
        --restart always \
        -e "MESOS_HOSTNAME=${HOST_IP}" \
        -e "MESOS_IP=${HOST_IP}" \
        -e "MESOS_ZK=zk://${HOST_IP}:2181/mesos" \
        -e "MESOS_PORT=5050" \
        -e "MESOS_LOG_DIR=/var/log/mesos" \
        -e "MESOS_QUORUM=1" \
        -e "MESOS_REGISTRY=in_memory" \
        -e "MESOS_WORK_DIR=/var/lib/mesos" \
        mesoscloud/mesos-master

    docker run -d \
        --net host \
        --name kolla_marathon \
        --restart always \
        -e "MARATHON_HOSTNAME=${HOST_IP}" \
        -e "MARATHON_HTTPS_ADDRESS=${HOST_IP}" \
        -e "MARATHON_HTTP_ADDRESS=${HOST_IP}" \
        -e "MARATHON_MASTER=zk://${HOST_IP}:2181/mesos" \
        -e "MARATHON_ZK=zk://${HOST_IP}:2181/marathon" \
        mesoscloud/marathon

    docker run -d \
        --net host \
        --name kolla_chronos \
        --restart always \
        -e "CHRONOS_HTTP_PORT=4400" \
        -e "CHRONOS_MASTER=zk://${HOST_IP}:2181/mesos" \
        -e "CHRONOS_ZK_HOSTS=${HOST_IP}:2181" \
        mesoscloud/chronos

    docker run -d \
        --net host \
        --privileged \
        --name kolla_mesos_slave_1 \
        --restart always \
        --entrypoint="mesos-slave" \
        -e "MESOS_HOSTNAME=${HOST_IP}" \
        -e "MESOS_IP=${HOST_IP}" \
        -e "MESOS_MASTER=zk://${HOST_IP}:2181/mesos" \
        -e "MESOS_LOG_DIR=/var/log/mesos" \
        -e "MESOS_LOGGING_LEVEL=INFO" \
        -v /sys/fs/cgroup:/sys/fs/cgroup \
        -v /var/run/docker.sock:/var/run/docker.sock \
        mesoscloud/mesos-slave

    echo "Mesos    > http://${HOST_IP}:5050"
    echo "Marathon > http://${HOST_IP}:8080"
    echo "Chronos  > http://${HOST_IP}:4400"
}

function infra_stop {
    docker rm -f $(docker ps -a -q --filter="name=kolla")
}

function usage {
    cat <<EOF
Usage: $0 COMMAND [options]

Options:
    --host, -i <host_ip> Specify path to host ip
    --net-iface, -n <nic> Specify NIC to use for host ip lookup
    --help, -h                       Show this usage information

Commands:
    start  Start required infrastructure
    stop  Stop required infrastructure
EOF
}

ARGS=$(getopt -o hin: -l help,host,net-iface: --name "$0" -- "$@") || { usage >&2; exit 2; }
eval set -- "$ARGS"

while [ "$#" -gt 0 ]; do
    case "$1" in
        (--host|-i)
            HOST_IP="$2"
            shift 2
            ;;

        (--net-iface|-n)
            NET_IFACE="$2"
            HOST_IP=$(get_host_ip)
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
