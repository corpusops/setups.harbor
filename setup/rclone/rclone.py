#!/usr/bin/env python3
#
"""
rclone based backup:
- each backup will backup :
    - the local database backups
    - one rclone remote (containing registry files)
    - the previous remote backup is server side copied to save bandwith prior to backup (sync mode)
- This also include a healthcheck for heathcheck (call with --healthcheck)
- Backups are rotated and only --keep are kept.
"""
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
from collections import OrderedDict
import os
import re
import sys
import argparse
import datetime
import subprocess
import json


HOURS = 60 * 60
DAYS = HOURS * 24
LOCK_TIMEOUT = 1 * DAYS
DTFMT = '%Y-%m-%d_%H%M%S'
src = os.environ['RCLONE_SRC']
dest = os.environ['RCLONE_DEST']
dt = datetime.datetime.now()
ts = int(dt.timestamp())
rclone = 'rclone --config {rclone_conf}'
sdt = dt.strftime(DTFMT)
rclone_sync_command = '{rclone} sync -vvv {l} {d}'
rclone_syncold_command = '{rclone} sync -vvv {o} {d}'
cmds = {
    'ldata': {'l': '/ldata/',
              'o': '{rclone_remote}:{dest}/{olddt}/ldata/',
              'd': '{rclone_remote}:{dest}/{sdt}/ldata/'},
    'dbs': {'l': '/dbs/',
            'o': '{rclone_remote}:{dest}/{olddt}/dbs/',
            'd': '{rclone_remote}:{dest}/{sdt}/dbs/'},
    'data': {'l': '{rclone_remote_src}:{src}/',
             'o': '{rclone_remote}:{dest}/{olddt}/data/',
             'd': '{rclone_remote}:{dest}/{sdt}/data/'}
}
datadir = '/var/log/rclone'
log = f'{datadir}/status.json'
LOCK = f'{datadir}/status.lock'
backup_status_path = f'{datadir}/{{k}}/{{sdt}}'
_data = {
    'out': '',
}


def as_bool(value):
    if isinstance(value, str):
        return bool(re.match("^(y|o|1|t)", value.lower()))
    else:
        return bool(value)


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
    pr = subprocess.run(c, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
    if record_output:
        _data['out'] += pr.stdout.decode() + '\n'
    return pr


def get_output():
    return _data['out']


def reset_output():
    _data['out'] = ''


def load_logs(currentlog=None):
    currentlog = currentlog or OrderedDict()
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
    if len(currentlog):
        logdata[sdt] = currentlog
    return logdata


def healthcheck(opts, lastlog=None, olddt=None):
    ts = int(dt.timestamp())
    healthcheckmsg, perfdata = '', {}
    if not lastlog:
        ret = 2
        healthcheckmsg += ' - NoStatus'
    else:
        ret = bool([a for a in lastlog if a != 'rotate' and lastlog[a]['ret'] != 0]) and 2 or 0
        for a, ka in lastlog.items():
            if a == 'rotate':
                continue
            if ka['ts'] + opts.freshness_crit <= ts:
                ret = 2
                healthcheckmsg += f' - CRIT: stale {a}'
            elif ka['ts'] + opts.freshness_warn <= ts:
                ret = 1
                healthcheckmsg += f' - WARN: stale {a}'
            for i in ['elapsed', 'ts']:
                perfdata[f"{a}_{i}"] = ka[i]
    # if in monit out, bail out with monit status
    perfdata = ';'.join([f'{a}={v}' for a, v in perfdata.items()]).strip()
    if not healthcheckmsg:
        healthcheckmsg = f'{ret == 0 and f"OK - {olddt}" or "ERROR"}'
    healthcheckmsg += f'{perfdata and ("|"+perfdata) or ""}'
    print(healthcheckmsg)
    sys.exit(ret)


def get_last_log(logdata):
    lastlog, olddt = None, None
    if logdata:
        olddt = [a for a in logdata if 'data' in logdata[a]][-1]
        lastlog = logdata[olddt]
    return lastlog, olddt


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
    if as_bool(os.environ.get('HARBOR_BACKUP_DISABLED', '1')):
        print('Backup disabled, '
              'export HARBOR_BACKUP_DISABLED=0 to reenable replication')
        sys.exit(0)
    parser = argparse.ArgumentParser()
    parser.add_argument('--dont-use-old', action="store_true", default=False)
    parser.add_argument('--rotate_only', action="store_true", default=False)
    parser.add_argument('--healthcheck', action="store_true", default=False)
    parser.add_argument('--freshness-warn', action="store", default=DAYS * 7, type=int)
    parser.add_argument('--freshness-crit', action="store", default=DAYS * 11, type=int)
    parser.add_argument('--keep', default=4, type=int)
    parser.add_argument('--rclone-config', default=os.environ.get('RCLONE_CONFIG', '/w/rclone.conf'))
    parser.add_argument('--rclone-remote', default=os.environ.get('RCLONE_REMOTE'))
    parser.add_argument('--rclone-remote-src', default=os.environ.get('RCLONE_REMOTE_SRC'))
    opts = parser.parse_args()
    assert opts.rclone_remote
    assert opts.rclone_remote_src
    logdata = load_logs()
    lastlog, olddt = get_last_log(logdata)
    if opts.healthcheck:
        return healthcheck(opts, olddt=olddt, lastlog=lastlog)
    lock = Lock.acquire()
    try:
        ret = _main(opts, logdata, lastlog, olddt)
    finally:
        lock.release()
    return ret


def _main(opts, logdata, lastlog, olddt):
    ret = 0
    rclone_remote = opts.rclone_remote
    rclone_remote_src = opts.rclone_remote_src
    rclone_conf = opts.rclone_config
    currentlog = OrderedDict()
    if not opts.rotate_only:
        for k, kd in cmds.items():
            globs = globals()
            globs.update(locals())
            for i in (
                'sdt', 'olddt', 'rclone', 'dest', 'src', 'rclone_conf',
                'rclone_remote', 'rclone_remote_src',
                'rclone_sync_command', 'rclone_syncold_command',
            ):
                kd.setdefault(i, globs[i])
            kd = dict_resolve(kd)
            c, soc = kd['rclone_sync_command'], kd['rclone_syncold_command']
            # real backup is done here
            cdt = datetime.datetime.now()
            ret, rotate = 0, True
            if olddt and (kd['o'] != kd['d']) and not opts.dont_use_old:
                # remote copy last backup if any to make incremental backups quickier but also save bandwidth
                pr = crun(soc)
                ret = pr.returncode
            if ret == 0:
                pr = crun(c)
            ret = (pr.returncode != 0) and 1 or 0
            ndt = datetime.datetime.now()
            secs = (ndt - cdt).total_seconds()
            currentlog[k] = {
                'ts': int(cdt.timestamp()),
                'ret': ret,
                'elapsed': secs,
                'out': get_output(),
            }
            reset_output()
    # if we ran up to there, run rotate routine and cleanup old backups
    # We filter out rotate only runs and also remove old rotate only jobs
    logdata = OrderedDict([(a, d)
                           for a, d in load_logs(currentlog=currentlog).items()
                           if 'data' in d])
    tocleanup = [a for ix, a in enumerate(reversed(logdata), 1) if ix > opts.keep]
    tocleanup.reverse()
    ret = 0
    cdt = datetime.datetime.now()
    for bck in tocleanup:
        globs = globals()
        globs.update(locals())
        cmd = f'{rclone} delete -vvv {rclone_remote}:{dest}/{bck}'.format(**globs)
        pr = crun(cmd)
        if pr.returncode != 0:
            ret = 1
        else:
            logdata.pop(bck, None)
    ndt = datetime.datetime.now()
    secs = (ndt - cdt).total_seconds()
    currentlog['rotate'] = {
        'ts': cdt.timestamp(),
        'elapsed': secs,
        'out': get_output(),
        'ret': ret,
    }
    if len(currentlog):
        logdata = load_logs(currentlog=currentlog)
        jlog = jdump(logdata)
        with open(log, 'w') as fic:
            fic.write(jlog)
    return ret


if __name__ == '__main__':
    main()
#
# vim:set et sts=4 ts=4 tw=120:
