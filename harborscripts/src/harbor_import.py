#!/usr/bin/env python
# -*- coding: utf-8 -*
from __future__ import absolute_import, division, print_function

import copy
from collections import OrderedDict
import requests
from harbor_utils import (
    # noqa
    filter_dict,
    harbor_api,
    EXPORTFILE,
    DEFAULT_ROBOT_PERMISSION,
    DEFAULT_ROBOT,
    get_username,
    get_harbor_batched as get_batched,
    default,
    setup,
    create_robot,
    update_robot_secret,
    ensure_harbor_connected,
    get_or_create_robot,
    L)


def main():
    """."""
    exportfile = EXPORTFILE
    export = setup(exportfile=exportfile)
    current_user = ensure_harbor_connected()  # noqa
    robots = OrderedDict([(a['name'], a) for a in get_batched('/robots')])
    users = OrderedDict([(a['realname'], a) for a in get_batched('/users')])
    namespaces = OrderedDict([(a['name'], a) for a in get_batched('/projects')])
    if not namespaces:
        raise Exception('not connected')
    to_sync = OrderedDict()

    # select relevant namespaces
    for ns, ndata in export['namespaces'].items():
        # filter out imported namespaces without any tags
        nstags = list(sorted([
            a for a in export['images']
            if (export['images'][a]['namespace'] == ns and
                len(export['images'][a]['tags']))
        ]))
        if not nstags:
            continue
        ndata['tags'] = nstags
        to_sync[ns] = ndata

    # create namespaces
    for ns, ndata in to_sync.items():
        nstags = ndata['tags']
        if not ndata['groups']:
            nsusers = [ns]
        else:
            nsusers = []
            for g in ndata['groups']:
                nsusers.extend(export["groups"][g]["users"])
        try:
            _ = namespaces[ns]
        except KeyError:
            ret = harbor_api(
                '/projects', method='post',
                json={"project_name": ns, "metadata": {"public": "False"},
                      "storage_limit": -1, "registry_id": None})
            assert ret.status_code == 201
            namespaces[ns] = harbor_api(ret.headers['Location'], force_uri=True).json()
            L.info(f'Created project: {ns}')

    # create robots
    for user, udata in export['users'].items():
        if not udata['bot']:
            continue
        _ = get_or_create_robot(
            user,
            udata['namespaces'],
            robots=robots,
            namespaces=namespaces,
            secret=export['tokens'].get(user, None))


if __name__ == '__main__':
    main()

# vim:set et sts=4 ts=4 tw=120:
