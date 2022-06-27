#!/usr/bin/env python
# -*- coding: utf-8 -*
from __future__ import absolute_import, division, print_function

import copy
from collections import OrderedDict
import requests
from harbor_utils import (
    # noqa
    harbor_api,
    EXPORTFILE,
    get_harbor_batched as get_batched,
    setup,
    get_harbor_data,
    ensure_harbor_connected,
    L)


def main():
    """."""
    L.info('start')
    exportfile = EXPORTFILE
    _ = setup(exportfile=exportfile)
    hdata = get_harbor_data()
    current_user = ensure_harbor_connected()  # noqa
    namespaces = OrderedDict([(a['name'], a) for a in get_batched('/projects')])
    if not namespaces:
        raise Exception('not connected')

    # create namespaces
    for ns, ndata in hdata['projects'].items():
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
    L.info('end')


if __name__ == '__main__':
    main()

# vim:set et sts=4 ts=4 tw=120:
