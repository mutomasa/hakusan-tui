#!/bin/bash
# 役割: ctl（slurmdbd + slurmctld） / node（slurmd）
set -euo pipefail
ROLE="${1:-node}"
service munge start >/dev/null

# slurmd 用に cgroup v2 を整える（ルートのプロセスを init に退避し、コントローラを委譲）
prepare_cgroup() {
  local cg=/sys/fs/cgroup
  mkdir -p "$cg/init" "$cg/system.slice"
  while read -r pid; do echo "$pid" > "$cg/init/cgroup.procs" 2>/dev/null || true; done < "$cg/cgroup.procs"
  for c in $(cat "$cg/cgroup.controllers"); do echo "+$c" > "$cg/cgroup.subtree_control" 2>/dev/null || true; done
}

wait_port() { until nc -z "$1" "$2" 2>/dev/null; do sleep 1; done; }

if [ "$ROLE" = "ctl" ]; then
  for u in testuser otheruser; do
    mkdir -p "/home/$u" && chown "$u:$u" "/home/$u"
  done
  wait_port db 3306
  slurmdbd
  wait_port localhost 6819
  sacctmgr -i add cluster hakusan-test >/dev/null 2>&1 || true
  exec slurmctld -D -i
else
  prepare_cgroup
  # 偽GPUデバイス（ドライバなし。数を数えるためだけ）
  for i in 0 1; do [ -e /dev/nvidia$i ] || mknod /dev/nvidia$i c 195 $i; done
  wait_port ctl 6817
  exec slurmd -D -N "$(hostname)"
fi
