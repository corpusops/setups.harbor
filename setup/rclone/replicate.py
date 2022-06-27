#!/usr/bin/env python3
"""
replication script:
    - will stop dest stack
    - sync db
    - sync s3 bucket
    - sync local data
    - restart stack
    - stop dest replications
- This also include a healthcheck for heathcheck (call with --healthcheck)
- Logs are rotated and only --keep are kept.
"""
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
from collections import OrderedDict
import os
import sys
import re
import argparse
import datetime
import subprocess
import json


HOURS = 60 * 60
DAYS = HOURS * 24
LOCK_TIMEOUT = 1 * DAYS
DTFMT = '%Y-%m-%d_%H%M%S'
replicate_dbs = os.environ.get(
    'REPLICATE_DBS', 'notarysigner notaryserver registry'
)
rclone_remote_src = os.environ['RCLONE_REMOTE_SRC']
rclone_src = os.environ['RCLONE_SRC']
rclone_remote_replicate = os.environ['RCLONE_REMOTE_REPLICATE']
rclone_replicate = os.environ['RCLONE_REPLICATE']
replicate_host = os.environ.get('HARBOR_REPLICATE_SSH_HOST', 'ssh-replicate')
replicate_host_path = os.environ['HARBOR_REPLICATE_HOST_PATH']
replicate_url = os.environ['HARBOR_REPLICATE_URL']
harbor_username = os.environ['HARBOR_USERNAME']
harbor_password = os.environ['HARBOR_PASSWORD']
replicate_local_data_path = os.environ['HARBOR_REPLICATE_LOCAL_DATA_PATH']
stop_stack_replicate_script = '''
ssh -ttt {replicate_host} bash<<EOF
set -e
cd "{replicate_host_path}"
docker-compose stop -t 0
EOF
'''
up_db_replicate_script = '''
set -e
ssh -ttt {replicate_host} bash<<EOF
set -e
cd "{replicate_host_path}"
docker-compose up -d --no-deps log postgresql
docker-compose exec -T postgresql bash <<CEOF
while ! ( echo select 1|psql -v ON_ERROR_STOP=1 $POSTGRES_DB; );do
    sleep 1;echo waitingPg;done
CEOF
EOF
'''
sync_db_replicate_script = '''
set -e
for i in {replicate_dbs};do
pg_dump -Fc --host=postgresql --username=$POSTGRES_USER $i\
        | ssh -ttt {replicate_host} bash -c '\
        set -e &>/dev/null\
        && cd {replicate_host_path} \
        && docker-compose exec -T postgresql \
        pg_restore --no-owner --if-exists --clean -d '"$i"
done
'''  # noqa
sync_bucket_replicate_script = '''
set -e
{rclone_sync_command}
'''
sync_data_replicate_script = '''
set -e
rsync -aAHzv --numeric-ids /ldata/ {replicate_host}:{replicate_local_data_path}/ \
  --exclude=/redis --exclude=/database --exclude=/job_logs
'''
reconfigure_replicate_script = '''
set -e
'''
restart_replicate_script = '''
set -e
ssh -ttt {replicate_host} bash<<EOF
set -e
cd "{replicate_host_path}"
docker-compose stop -t 0
docker-compose up -d
EOF
URL="{replicate_url}"
while true;do
    ret=$(curl -s -m 3 -u "$HARBOR_USERNAME:$HARBOR_PASSWORD" $URL/api/v2.0/ping || true)
    if [ "xPong" != "x$ret" ];then
        echo "Wait registry to be up"
        sleep 1
    else
        break
    fi
done
'''
disable_replications_replicate_script = '''
set -e
ssh -ttt {replicate_host} bash<<EOF
set -e
cd "{replicate_host_path}/scripts"
docker-compose run --rm harborscripts src/harbor_toggle_replications.py --toggle=0
EOF
'''
dt = datetime.datetime.now()
ts = int(dt.timestamp())
rclone = 'rclone --config {rclone_conf}'
sdt = dt.strftime(DTFMT)
rclone_sync_command = '{rclone} sync -vvv {local_rclone} {dest_rclone}'
local_rclone = '{rclone_remote_src}:{rclone_src}'
dest_rclone = '{rclone_remote_replicate}:{rclone_replicate}'
datadir = '/var/log/rclone'
log = f'{datadir}/replicatestatus.json'
LOCK = f'{datadir}/replicatestatus.lock'
backup_status_path = f'{datadir}/{{k}}/{{sdt}}'
_data = {
    'out': '',
}


def jdump(d):
    return json.dumps(d, indent=2)


def dict_resolve(kd, steps=2, isteps=None):
    if isteps is None:
        isteps = steps
    for i in range(steps):
        for k in [a for a in kd]:
            for i in range(isteps):
                val = kd[k]
                if not isinstance(val, str):
                    continue
                kd[k] = val.format(**kd)
    return kd


def crun(c, record_output=True, *a, **kw):
    print(f'Running {c}')
    pr = subprocess.run(c, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        shell=True)
    out = pr.stdout.decode()
    if record_output:
        _data['out'] += out + '\n'
    return pr


def get_output():
    return _data['out']


def reset_output():
    _data['out'] = ''


def load_logs():
    if not os.path.exists(datadir):
        os.makedirs(datadir)
    if not os.path.exists(log):
        with open(log, 'w') as fic:
            fic.write('{}')
    with open(log, 'r') as fic:
        try:
            logdata = json.load(fic, object_pairs_hook=OrderedDict)
        except json.decoder.JSONDecodeError:
            logdata = OrderedDict()
    return logdata


def healthcheck(logdata, opts, perfdata=None, ret=0, msg=None):
    lastlog, olddt = None, None
    if logdata:
        olddt, lastlog = list(logdata.items())[-1]
    msg = msg or ''
    perfdata = perfdata or OrderedDict()
    lastlog = lastlog or OrderedDict()
    if not lastlog:
        ret = 2
        msg += ' - NoStatus'
    else:
        # ret = bool([a for a in lastlog if a != 'rotate' and lastlog[a]['ret'] != 0]) and 2 or 0
        try:
            lj = list(lastlog.values())[-1]
        except IndexError:
            lj = {'ret': 1, 'out': 'Never ran', 'ts': 0, 'elapsed': 0}
        cret, out, lastts = lj['ret'], lj['out'], lj['ts']
        elapsed = sum([float(a['elapsed']) for a in lastlog.values()])
        slastts = datetime.datetime.fromtimestamp(lastts).isoformat()
        if cret != 0:
            ret = 2
            msg += f' - CRIT: replication is broken: {out}'
        elif lastts + opts.freshness_crit <= ts:
            ret = 2
            msg += f' - CRIT: stale replication ({lastts}/{slastts})'
        elif lastts + opts.freshness_warn <= ts:
            ret = 1
            msg += f' - WARN: stale replication({lastts}/{slastts})'
        for i in ['elapsed', 'lastts']:
            perfdata[i] = locals()[i]
    olddt = olddt and olddt or None
    perfdata = perfdata or {}
    # if in monit out, bail out with monit status
    perfdata = ';'.join([f'{a}={v}' for a, v in perfdata.items()]).strip()
    if not msg:
        msg = f'{ret == 0 and f"OK - {olddt}" or "ERROR"}'
    msg += f'{perfdata and ("|"+perfdata) or ""}'
    print(msg)
    sys.exit(ret)


def get_globs(locs):
    globs = globals()
    globs.update(locs)
    fglobs = dict([(a, v) for a, v in globs.items()
                   if re.search('^harbor_|dt|rclone|replicate|dest|src', a)])
    return dict_resolve(fglobs)


def as_bool(value):
    if isinstance(value, str):
        return bool(re.match("^(y|o|1|t)", value.lower()))
    else:
        return bool(value)


def do_step(currentlog, kd, step):
    cmd = f'{step}_replicate_script'
    c = kd[cmd]
    # real backup is done here
    cdt = datetime.datetime.now()
    skip = as_bool(
        os.environ.get(
            f'SKIP_{cmd}',
            os.environ.get(
                f'SKIP_{cmd}',
                os.environ.get(
                    f'SKIP_{cmd}'.upper(),
                    os.environ.get(
                        f'SKIP_{step}',
                        os.environ.get(
                            f'skip_{step}',
                            os.environ.get(
                                f'skip_{step}'.upper(),
                                '0')))))))
    if not skip:
        pr = crun(c)
        ret = (pr.returncode != 0) and 1 or 0
        out = get_output()
        reset_output()
    else:
        ret, out = 0, '>>> SKIPPED'
    ndt = datetime.datetime.now()
    secs = (ndt - cdt).total_seconds()
    ret = currentlog[step] = {
        'ts': int(cdt.timestamp()),
        'ret': ret,
        'elapsed': secs,
        'out': out,
    }
    if ret['out'].strip():
        print(f'Step {step}:\n{ret["out"]}\n')
    return ret


class Lock(Exception):

    def __init__(self, lock=None, timeout=None, *a, **kw):
        Exception.__init__(self, *a, **kw)
        self.lock = lock or LOCK
        self.timeout = timeout or LOCK_TIMEOUT

    @property
    def locktime(self):
        locktime = None
        if os.path.exists(self.lock):
            with open(self.lock, 'r') as fic:
                locktime = fic.read()
        return locktime

    @property
    def message(self):
        return f"{self.lock} is locked: {self.locktime}"

    def __str__(self):
        return self.message

    def write(self):
        d = os.path.dirname(self.lock)
        if not os.path.exists(d):
            os.makedirs(d)
        with open(self.lock, 'w') as fic:
            print(f'Locking {self.lock}')
            fic.write(sdt)

    def release(self):
        if os.path.exists(self.lock):
            print(f'Releasing {self.lock}')
            os.unlink(self.lock)

    @classmethod
    def acquire(kls, lock=LOCK, timeout=LOCK_TIMEOUT):
        self = kls(lock=lock, timeout=timeout)
        if self.locktime:
            st = os.stat(self.lock)
            ts = int(datetime.datetime.now().timestamp())
            try:
                lockts = int(datetime.datetime.strptime(self.locktime, DTFMT).timestamp())
            except Exception:
                lockts = int(st.st_ctime)
            if (lockts + self.timeout) <= ts:
                print(f"{self.lock} is stale, removing: {self.locktime}")
                self.release()
            else:
                raise self
        self.write()
        return self


def main():
    if as_bool(os.environ.get('HARBOR_REPLICATION_DISABLED', '1')):
        print('Replication disabled, '
              'export HARBOR_REPLICATION_DISABLED=0 to reenable replication')
        sys.exit(0)
    parser = argparse.ArgumentParser()
    parser.add_argument('--healthcheck', action="store_true", default=False)
    parser.add_argument('--keep', action="store", default=365, type=int)
    parser.add_argument('--freshness-warn', action="store", default=HOURS * 2, type=int)
    parser.add_argument('--freshness-crit', action="store", default=DAYS * 1, type=int)
    parser.add_argument('--rclone-config', default=os.environ.get('RCLONE_CONFIG', '/w/rclone.conf'))
    opts = parser.parse_args()
    logdata = load_logs()
    if opts.healthcheck:
        return healthcheck(logdata, opts=opts)
    lock = Lock.acquire()
    try:
        ret = _main(opts, logdata)
    finally:
        lock.release()
    return ret


def _main(opts, logdata):
    rclone_conf = opts.rclone_config
    kd = dict_resolve(get_globs(locals()))
    currentlog = OrderedDict()
    for step in [
        # stop fallback stack
        'stop_stack',
        # start fallback db
        'up_db',
        # sync fallback db
        'sync_db',
        # sync fallback buckets
        'sync_bucket',
        # sync fallback extra data
        'sync_data',
        # reconfigure if any
        'reconfigure',
        # restart stack
        'restart',
        #  disable_replications
        'disable_replications',
    ]:
        ret = do_step(currentlog, kd, step)
        if ret['ret'] != 0:
            break
    logdata = load_logs()
    if len(currentlog):
        logdata[sdt] = currentlog
    # if we ran up to there, run rotate routine and cleanup old backups
    # filter out rotate only runs and also remove old rotate only jobs
    logdata = OrderedDict(reversed([
        a for ix, a in enumerate(reversed(logdata.items()), 1)
        if ix <= opts.keep]))
    if len(currentlog):
        jlog = jdump(logdata)
        with open(log, 'w') as fic:
            fic.write(jlog)
    return ret


if __name__ == '__main__':
    main()
#
# vim:set et sts=4 ts=4 tw=120:
