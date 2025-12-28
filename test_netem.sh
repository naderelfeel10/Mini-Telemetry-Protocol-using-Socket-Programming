#!/bin/bash

IFACE=lo

clear_netem() {
    sudo tc qdisc del dev $IFACE root 2>/dev/null
}

baseline() {
    echo "=== BASELINE TEST ==="
    clear_netem
}

loss_test() {
    echo "=== LOSS 5% TEST ==="
    clear_netem
    sudo tc qdisc add dev $IFACE root netem loss 5%
}

delay_test() {
    echo "=== DELAY + JITTER TEST ==="
    clear_netem
    sudo tc qdisc add dev $IFACE root netem delay 100ms 10ms
}

case "$1" in
    baseline)
        baseline
        ;;
    loss)
        loss_test
        ;;
    delay)
        delay_test
        ;;
    clean)
        clear_netem
        ;;
    *)
        echo "Usage: $0 {baseline|loss|delay|clean}"
        exit 1
esac
