# 開発ガイド

## 構成

```text
src/hakusan_tui/
  app.py              Textual App（9タブ、キー、更新、キャンセル/対話ジョブの流れ）
  cli.py config.py    起動オプション / TOML 設定
  models.py i18n.py   共通モデル / 日本語の状態・待機理由
  validation.py formatting.py context.py
  adapters/
    base.py           ClusterAdapter Protocol（UI はこれだけに依存）
    slurm.py          Slurm CLI アダプター（Capability Detection、JSON→テキストのフォールバック）
    slurm_parsers.py  squeue JSON/テキスト、scontrol -o、sacct の解析
    gpu.py            GRES/TRES から GPU 割当（重複排除・分割GPU分離・不明は None）
    hakusan.py        spart 解析・パーティション分類
    tools.py          読み取り専用ツールのホワイトリスト（module / qstat / sstat）
    demo.py           デモ（resources/demo_data を本番と同じパーサーで読む）
  services/           command_runner（argv 実行・timeout・上限）、refresh（TTL・単一フライト）、
                      jobs（キャンセル安全確認）、submission、logs、interactive、diagnostics
  screens/ widgets/   各タブ / 共通部品
```

## テスト

```bash
uv run pytest -q          # 単体 + UI（Slurm 不要。tests/integration は -m slurm 指定時のみ）
uv run ruff check .
```

### Docker 上の実 Slurm で結合テスト

```bash
docker compose -f docker/compose.yml up -d --build
docker compose -f docker/compose.yml exec ctl sinfo          # idle になるまで十数秒待つ
docker compose -f docker/compose.yml exec ctl /work/docker/run-integration.sh
docker compose -f docker/compose.yml exec ctl /work/docker/run-integration.sh -k staging  # 絞り込み
docker compose -f docker/compose.yml down -v
```

クラスタ構成（テスト専用・HAKUSAN の実構成ではない）:

| コンテナ | 役割 |
|---|---|
| `db` | MariaDB（accounting） |
| `ctl` | munge + slurmdbd + slurmctld。プロジェクトを `/work` にマウント。テストはここで `testuser` として実行 |
| `lcpcc-001` | CPU ノード（4 CPU / 2000 MiB）。パーティション DEF（既定）, TINY |
| `spcc-a40g01` | 偽 GPU ノード（`gpu:a40:2`、`/dev/nvidia[0-1]` は mknod したダミー）。GPU-1, GPU-S |

- `/home` は名前付きボリュームで全ノード共有（ジョブのログ出力先）。
- Prolog / TaskProlog / Epilog で HAKUSAN の `$JOBDIR`（`/JOBs/<jobid>`、ジョブ終了で削除）を模倣。
- Lmod とテスト用 modulefiles（`gcc/13.2.0`, `cuda/12.4`）、`spart` スタブ入り。
- 計算ノードは slurmd 23.11 が cgroup v2 を必須とするため `privileged` + `cgroup: private` + `init: true`。

### TUI を実 Slurm で触る

```bash
docker compose -f docker/compose.yml exec -u testuser -w /work ctl \
  env UV_PROJECT_ENVIRONMENT=/opt/venv uv run --frozen hakusan-tui
```

### フィクスチャ

`tests/fixtures/slurm-23.11/` は上記クラスタで採取した実出力。ジョブ名に `|` を含むジョブ
（`train vla|x`）を意図的に入れ、区切り文字問題の回帰テストに使っている。
