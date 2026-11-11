# hakusan-tui 結合テスト用 Slurm イメージ（ctl / 計算ノード共通）
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      slurm-wlm slurmdbd slurm-client munge mariadb-client lmod \
      python3 python3-venv ca-certificates procps iproute2 netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.7.9 /uv /usr/local/bin/uv

# 全コンテナで同じ munge 鍵・ユーザーUIDを使う（テスト専用）
RUN dd if=/dev/urandom of=/etc/munge/munge.key bs=1 count=1024 status=none \
    && chown munge:munge /etc/munge/munge.key && chmod 400 /etc/munge/munge.key \
    && useradd -m -u 2001 -s /bin/bash testuser \
    && useradd -m -u 2002 -s /bin/bash otheruser \
    && mkdir -p /var/spool/slurmctld /var/spool/slurmd /var/log/slurm /JOBs \
    && chown slurm:slurm /var/spool/slurmctld /var/log/slurm \
    && chmod 1777 /JOBs

COPY etc/slurm.conf etc/gres.conf etc/cgroup.conf etc/prolog.sh etc/epilog.sh etc/task_prolog.sh /etc/slurm/
RUN chmod 755 /etc/slurm/prolog.sh /etc/slurm/epilog.sh /etc/slurm/task_prolog.sh
COPY etc/slurmdbd.conf /etc/slurm/slurmdbd.conf
RUN chown slurm:slurm /etc/slurm/slurmdbd.conf && chmod 600 /etc/slurm/slurmdbd.conf
COPY modulefiles /opt/modulefiles
COPY etc/modules.sh /etc/profile.d/zz-hakusan-modules.sh
COPY bin/spart /usr/local/bin/spart
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/spart /usr/local/bin/entrypoint.sh

ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_CACHE_DIR=/opt/uv-cache UV_LINK_MODE=copy
RUN mkdir -p /opt/venv /opt/uv-cache && chmod 1777 /opt/venv /opt/uv-cache
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
