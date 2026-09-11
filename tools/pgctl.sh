#!/usr/bin/env bash
# 本地便携版 PostgreSQL 控制脚本（无需 root / apt 安装），端口 55433
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PGHOME="$HERE/pgroot/usr/lib/postgresql/15"
PGDATA="$HERE/pgdata"
export LD_LIBRARY_PATH="$PGHOME/lib"

case "${1:-status}" in
  start)
    "$PGHOME/bin/pg_ctl" -D "$PGDATA" -l "$HERE/pgrun/startup.log" -w start
    ;;
  stop)
    "$PGHOME/bin/pg_ctl" -D "$PGDATA" -w stop
    ;;
  restart)
    "$0" stop; "$0" start
    ;;
  status)
    "$PGHOME/bin/pg_ctl" -D "$PGDATA" status
    ;;
  psql)
    shift
    "$PGHOME/bin/psql" -h 127.0.0.1 -p 55433 -U postgres "$@"
    ;;
  *)
    echo "用法: $0 {start|stop|restart|status|psql}"
    exit 1
    ;;
esac
