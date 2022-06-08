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
    DEFAULT_ACCESS,
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
    sortperm,
    equivalent_permissions,
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
    # link users to projects
    for ns, nsdata in to_sync.items():
        husers = []
        _ = [husers.append(u) for u in
             sorted(
                 sum([export['groups'][g]['users'] for g in nsdata['groups']], [])
             )
             if u not in husers and not export['users'][u]['bot']]
        L.info('Updating {user} user permissions')
        project = namespaces[ns]
        members = harbor_api(f'/projects/{project["project_id"]}/members').json()
        memberperms = dict([(a['entity_name'], {'role': a['role_id'],
                                                'perm': a}) for a in members])
        patched = False
        for huser in husers:
            try:
                user = users[huser]
            except KeyError:
                L.info(f'{huser} does not exist, skipping')
                continue
            try:
                curperm = memberperms[huser]
            except KeyError:
                ret = harbor_api(
                    f'/projects/{project["project_id"]}/members',
                    method='post', json={
                        'role_id': 1, 'member_user': {'username': huser}
                    })
                assert ret.status_code == 201
                L.info(f'Adding {huser} to {ns}')
                patched = True
            else:
                if curperm['role'] != 1:
                    ret = harbor_api(
                        f'/projects/{project["project_id"]}/members/{curperm["perm"]["id"]}',
                        method='put', json={'role_id': 1})
                    L.info(f'Editing {huser} as admin for {ns}')
                    assert ret.status_code == 200
                    patched = True

    # link existing users to their namespaces
    for user, udata in export['users'].items():
        if udata['bot']:
            L.info(f'Updating {user} bot permissions')
            bot = get_or_create_robot(
                user,
                udata['namespaces'],
                robots=robots,
                namespaces=namespaces,
                secret=export['tokens'].get(user, None))
            perms = OrderedDict()
            for p in bot['permissions']:
                perms[p['namespace']] = p
            patch = False
            for ns in udata['namespaces']:
                try:
                    nsperms = perms[ns]
                except KeyError:
                    continue
                if not equivalent_permissions(nsperms['access'], DEFAULT_ACCESS):
                    nsperms['access'] = copy.deepcopy(DEFAULT_ACCESS)
                    patch = True
            if patch:
                ret = harbor_api(f'/robots/{bot["id"]}', json=bot, method='put')
                assert ret.status_code == 200
                ret = harbor_api(f'/robots/{bot["id"]}').json()
                L.info(f'Updated {user} bot')

if __name__ == '__main__':
    main()

# vim:set et sts=4 ts=4 tw=120:
