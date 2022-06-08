#!/usr/bin/env python
# -*- coding: utf-8 -*
from __future__ import absolute_import, division, print_function

from harbor_utils import (
    # noqa
    filter_dict,
    EXPORTFILE,
    setup,
    save,
    get_username,
    portus_api as api,
    L)


def export_structure(export, exportfile):
    PUSERS = export.setdefault('portusnames', {})
    USERS = export.setdefault('users', {})
    NAMESPACES = export.setdefault('namespaces', {})
    TOKENS = export.setdefault('tokens', {})
    GROUPS = export.setdefault('groups', {})
    ret = api('/users')
    for ix, item in enumerate(ret.json()):
        if (item['id'] in [1]):
            L.info(f'Skip {item["username"]}')
            continue
        item = filter_dict(item, ['id', 'username', 'email', 'admin', 'bot'])
        item['harborname'] = get_username(item)
        item['namespaces'] = []
        item.setdefault('groups', [])
        PUSERS[item['username']] = item['harborname']
        USERS[item['harborname']] = item
        L.info(f"Export USER: {item['harborname']}")
        if item['bot']:
            try:
                token = TOKENS[item["harborname"]]
            except KeyError:
                rtokens = api(f'/users/{item["id"]}/application_tokens').json()
                tokens = dict([(a["application"], a) for a in rtokens])
                for i in range(1000):
                    try:
                        _ = tokens[f'portusmigration{i}']
                    except KeyError:
                        break
                rtoken = api(f'/users/{item["id"]}/application_tokens', method='post',
                             json={'application': f'portusmigration{i}'}).json()
                token = rtoken["plain_token"]
            TOKENS[item["harborname"]] = item["token"] = token
            save(export, exportfile)
    ret = api('/namespaces')
    for ns in ret.json():
        if ns['id'] in [1]:
            continue
        ns = filter_dict(ns, ['id', 'name', 'description'])
        L.info(f"Export NS: {ns['name']}")
        NAMESPACES[ns['name']] = ns
        ns.setdefault('groups', [])
    ret = api('/teams')
    for ix, team in enumerate(ret.json()):
        team = filter_dict(team, ['id', 'name', 'description'])
        tn = team['name']
        L.info(f"Export team: {team['name']}")
        if team['id'] in [1]:
            continue
        namespaces = list(
            filter(
                lambda x: x['id'] not in [1],
                api(f'/teams/{team["id"]}/namespaces').json()))
        members = list(
            filter(
                lambda x: x['id'] not in [1],
                api(f'/teams/{team["id"]}/members').json()))
        group = GROUPS.setdefault(tn, team)
        group['members'] = [a['username'] for a in members]
        group['users'] = [PUSERS[a['username']] for a in members]
        group['namespaces'] = [a['name'] for a in namespaces]
        for ns in group['namespaces']:
            if tn not in NAMESPACES[ns]['groups']:
                NAMESPACES[ns]['groups'].append(tn)
        for user in group['users']:
            if tn not in USERS[user]['groups']:
                USERS[user]['groups'].append(tn)
            for ns in group['namespaces']:
                USERS[user]['namespaces'].append(ns)
    # complete groups
    save(export, exportfile)
    return export


def export_tags(export, exportfile):
    images = export.setdefault("images", {})
    images = export['images'] = {}
    repos = api('/repositories').json()
    for repo in repos:
        tags = [
            a["name"]
            for a in api(f'/repositories/{repo["id"]}/tags').json()]
        repo = filter_dict(repo, ['name', 'full_name', 'namespace'])
        repo['namespace_id'] = repo['namespace'].pop('id')
        repo['namespace'] = repo['namespace']['name']
        img = f'{repo["full_name"]}'
        L.info(f"Exported {img}")
        repo["tags"] = tags
        images[img] = repo
    save(export, exportfile)
    return export


def main():
    """."""
    exportfile = EXPORTFILE
    export = setup(exportfile=exportfile)
    export = export_structure(export, exportfile)
    export = export_tags(export, exportfile)
    save(export, exportfile)


if __name__ == '__main__':
    main()

# vim:set et sts=4 ts=4 tw=120:
