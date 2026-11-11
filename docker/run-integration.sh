#!/bin/bash
# ctl コンテナ内で実行する結合テスト。root で起動し、テストは testuser 権限で走らせる。
set -euo pipefail
if [ "$(id -u)" != "0" ]; then echo "root で実行してください" >&2; exit 1; fi

# 他ユーザーのジョブ（キャンセル拒否の確認用）
OTHER_JOB_ID=$(su otheruser -c "cd ~ && sbatch --parsable -p DEF -J other_job --wrap 'sleep 300'")
echo "otheruser のジョブ: $OTHER_JOB_ID"
trap 'scancel "$OTHER_JOB_ID" 2>/dev/null || true' EXIT

ARGS=$(printf ' %q' "$@")
su testuser -c "cd /work && export OTHER_JOB_ID=$OTHER_JOB_ID PYTHONDONTWRITEBYTECODE=1 \
  UV_PROJECT_ENVIRONMENT=$UV_PROJECT_ENVIRONMENT UV_CACHE_DIR=$UV_CACHE_DIR UV_LINK_MODE=copy && \
  uv run --frozen pytest -p no:cacheprovider -m slurm tests/integration -v $ARGS"
