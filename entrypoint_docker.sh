#!/bin/bash
set -e
redis-server /etc/redis/redis.conf &
python3 app.py
