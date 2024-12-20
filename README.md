# docker based harbor fullstack deployment using ansible

DISCLAIMER
============

**UNMAINTAINED/ABANDONED CODE / DO NOT USE**

Due to the new EU Cyber Resilience Act (as European Union), even if it was implied because there was no more activity, this repository is now explicitly declared unmaintained.

The content does not meet the new regulatory requirements and therefore cannot be deployed or distributed, especially in a European context.

This repository now remains online ONLY for public archiving, documentation and education purposes and we ask everyone to respect this.

As stated, the maintainers stopped development and therefore all support some time ago, and make this declaration on December 15, 2024.

We may also unpublish soon (as in the following monthes) any published ressources tied to the corpusops project (pypi, dockerhub, ansible-galaxy, the repositories).
So, please don't rely on it after March 15, 2025 and adapt whatever project which used this code.



See playbooks, set your variables and enjoy

ETA: WIP/not finished, may not be done


- can be used behind a SSL offloader
- adds a fail2ban integration to ban brute force attacks
- we currently use this branch until 2.4 : https://github.com/corpusops/harbor/tree/v2.3 to get job queues stable.


# export portus data and import into harbor
``.env`` (`harbor_harborscripts_dotenv` ansible setting)
```sh
DATA_FOLDER=/srv/docker/harbor/data/scripts
PORTUS_URL=https://portus
PORTUS_TOKEN=xxx:yyy
HARBOR_URL=https://harbor
HARBOR_USERNAME=xx
HARBOR_PASSWORD=xx
```

```sh
cd /srv/docker/harbor/current/harborscripts
docker-compose up -d
```


# upgrade
- remember the upgrade doc (verify on https://goharbor.io/docs/latest/administration/upgrade/)
- stop and install new stack and run migrate/prepare dance

    ```sh
    registry=
    inv=
    $COPS_ROOT/bin/ansible-playbook -vvvvD -l $registry -i $inv \
    deploy.yml -e "{cops_vars_debug: true}" \
    --skip-tags docker_setup,harbor_service_stope,harbor_download_installere,harbor_preparee,harbor_migratee,harbor_configs,harbor_service_start,post
    ```
- Then lookup configuration changes and adapt the template ``setup/harbor.yml``
- Then rerun in full

    ```sh
    registry=
    inv=
    $COPS_ROOT/bin/ansible-playbook -vvvvD -l $registry -i $inv \
    deploy.yml -e "{cops_vars_debug: true}" \
    --skip-tags docker_setup,harbor_service_stope,harbor_download_installere,harbor_prepare,harbor_migrate,harbor_configse,harbor_service_starte,poste
    ```

# make a emergency harbor release to patch a binary
prepare
```sh
git clone https://github.com/corpusops/harbor.git
cd harbor
git remote add goharbor https://github.com/goharbor/harbor.git
git fetch --all
git fetch goharbor  --tags
git reset --hard
git tag -l
git checkout v2.3.3 -b v2.3.3
cp make/harbor.yml.tmpl make/harbor.yml
$EDITOR make/harbor.yml
```

include your patch, for example cherry pick a commit of master
```
git cherry-pick
```

compile go binaries
```sh
make compile COMPILETAG=compile_golangimage NOTARYFLAG=true REGISTRYPROJECTNAME=corpusops REGISTRYPROJECTPREFIX=harbor- BASEIMAGENAMESPACE=corpusops
```

hack a one line dockerfile to include and patch the official image with your changes

```sh
v=v2.3.3
ns=corpusops
p=harbor-
echo "
FROM goharbor/harbor-registryctl:$v
ADD make/photon/registryctl/harbor_registryctl ./home/harbor/harbor_registryctl
" | docker build . -f- -t $ns/${p}registryctl:$v
echo "FROM goharbor/harbor-jobservice:$v
ADD make/photon/jobservice/harbor_jobservice ./
" | docker build . -f- -t $ns/${p}jobservice:$v
echo "FROM goharbor/harbor-core:$v
ADD make/photon/core/harbor_core ./
" | docker build . -f- -t $ns/${p}core:$v

```

# immediatly reclaim space after tag deletion
Force to reclaim space as GC wont go under 2 hours by default
```sh
docker-compose exec -u root jobservice sh -c "\
  curl -vvvv -XPOST -sSL localhost:8080/api/v1/jobs \
  -H 'Content-Type: application/json' \
  -H "'"Authorization: Harbor-Secret $CORE_SECRET"'" \
  --data-raw '"'{"job":{"name":"GARBAGE_COLLECTION","parameters":{"delete_untagged":true,"dry_run":false,"redis_url_reg":"redis://redis:6379/1?idle_timeout_seconds=30","time_window":0},"metadata":{"kind":"Generic","unique":false}}}'"'"
  ```



# Portus to Harbor import migration
```sh
# export portus structure
src/portus_export.py

# transform portus structure to harbor one
src/portus_to_harbor.py

# invite users (think to mail notify: --dryrun=0 (log instead of mail) --notify=0 (do not run notify at all))
src/harbor_invite.py      --dryrun=1
src/harbor_invite_ldap.py --dryrun=1

# create base namespaces
src/harbor_import_projects.py --dryrun=1

# link users to their projects
src/harbor_link.py --dryrun=1

# create replications
harbor_create_replications.py

## all at once (without notify)
harbor_update_replications.py

```


