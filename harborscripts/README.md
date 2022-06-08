# tools for working with harborscripts

## install as a python lib
```bash
pip install harborscripts
```

## Run in dev
### Configure
```bash
cp .env.dist .env
cp .env.local.dist .env.local
printf "USER_UID=$(id -u)\nUSER_GID=$(id -g)\n">>.env
```

### Build
```bash
eval $(egrep -hv '^#|^\s*$' .env .env.local|sed  -e "s/^/export /g"| sed -e "s/=/='/" -e "s/$/'/g"|xargs)
COMPOSE_FILE="docker-compose.yml:docker-compose-build.yml" docker-compose build
```

### Run

```bash
docker-compose run --rm app bash
```

```bash
sed "/COMPOSE_FILE/d" .env
echo COMPOSE_FILE=docker-compose.yml:docker-compose-dev.yml"
docker-compose up -d --force-recreate
docker-compose exec -u app app bash
```

### run tests
```bash
sed "/COMPOSE_FILE/d" .env
echo COMPOSE_FILE=docker-compose.yml:docker-compose-dev.yml:docker-compose-test.yml"
docker-compose exec -U app app tox -e linting,coverage
```

## Doc
see also [USAGE](./USAGE.md) (or read below on pypi)
