#!/usr/bin/env bash
cd "$(dirname $(readlink -f "$0"))"
dirs="
common/config/log
"
set -ex
for i in $dirs;do
    if [ -e "$i" ];then
        chown -Rfv root:root "$i"
        while read f;do chmod 0755 "$i";done <\
            <(find $i -type d)
        while read f;do chmod 0644 "$i";done <\
            <(find $i -type f)
    fi
done
if [ -e common.d ];then
    rsync -azv common.d/ common/
fi
# vim:set et sts=4 ts=4 tw=80:
