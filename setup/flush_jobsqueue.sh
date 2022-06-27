#!/usr/bin/env bash
cd "$(dirname $(readlink -f "$0"))"
set -ex
docker-compose exec -u root redis redis-cli flushdb
docker-compose exec -u root redis redis-cli -n 0 flushall
docker-compose exec -u root redis redis-cli -n 2 flushall
docker-compose up -d --no-deps --force-recreate jobservice core registryctl portal
# vim:set et sts=4 ts=4 tw=0:
