#!/bin/bash
set -e
echo never > /sys/kernel/mm/transparent_hugepage/enabled
sysctl vm.overcommit_memory=1
redis-server /etc/redis/redis.conf &
python3 app.py
