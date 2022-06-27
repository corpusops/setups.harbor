#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
import os
import sys
import click
import time
import re
from harbor_utils import (
    # noqa
    OrderedDict,
    harbor_api,
    EXPORTFILE,
    get_harbor_batched as get_batched,
    as_bool,
    setup,
    ensure_harbor_connected,
    Odict,
    stop_execs,
    L)


@click.option("--toggle", default=os.environ.get("REPLICATION_TOGGLE", "0"))
@click.option("--replication-match", default=os.environ.get("REPLICATION_MATCH", ".*"))
@click.command()
def main(**cli):
    o = Odict(cli)
    _ = setup(exportfile=EXPORTFILE)
    matcher = re.compile(o.replication_match, flags=re.I | re.U | re.S)
    current_user = ensure_harbor_connected()  # noqa
    toggle = as_bool(o.toggle)
    namespaces = OrderedDict([(a['name'], a) for a in get_batched('/projects')])
    if not namespaces:
        raise Exception('not connected')
    replications = OrderedDict([(a['name'], a) for a in get_batched('/replication/policies')])
    errors = []
    for repl, repl_data in replications.items():
        enabled = repl_data.get("enabled")
        repl_data["enabled"] = toggle
        match = repl
        if not matcher.search(match):
            print(f'{match} does not match target pattern: {o.replication_match}, skipping')
            continue
        # if executions are launched, and we are going to disable the replication, stop them first
        if enabled and not toggle:
            stop_execs(repl_data)
        # then toggle execution
        ret = harbor_api(
            f'/replication/policies/{repl_data["id"]}', method='put',
            json=repl_data)
        assert ret.status_code == 200
        L.info(f"Toggle to enabled={toggle} replication {repl_data['name']}")
    if errors:
        for i in errors:
            L.error(i)
        sys.exit(1)


if __name__ == "__main__":
    main()

# vim:set et sts=4 ts=4 tw=120:
