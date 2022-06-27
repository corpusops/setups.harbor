#!/usr/bin/env bash
cd $(dirname $(dirname $(readlink -f $0)))
docker-compose run --rm rclone /w/rclone.py --probe "$@"
# vim:set et sts=4 ts=4 tw=80:
