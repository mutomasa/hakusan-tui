# 作業履歴 — hakusan-tui

日々の作業内容・判断・課題を記録する。新しい日付を下に追記する。

## 2026-11-11

### やったこと

- `docs/slurm.md`（設計書 v1.0）を読み、`CLAUDE.md`、`todo.md`、本ファイルを作成。

### 判断・メモ

- 開発機（Linux, Docker 29, uv 0.7.9, Python 3.12）にはSlurmがないため、結合テストはDocker上に
  Slurmクラスタを立てて行う方針。
- Docker 上に Slurm 23.11.4 のテストクラスタを構築（`docker/`）。mariadb + slurmdbd + slurmctld（ctl）、
  CPUノード `lcpcc-001`、偽GPUノード `spcc-a40g01`（`gpu:a40:2`）。Lmod とテスト用 modulefiles、`spart` スタブ入り。
- 実クラスタの出力（squeue/sinfo JSON、scontrol -o、sacct、spart）を `tests/fixtures/slurm-23.11/` に採取。
- 本体を実装: models / i18n / パーサー / GPU集計 / spart解析 / コマンドランナー / キャッシュ /
  Slurm・デモアダプター / キャンセル・投入・ログ・診断・salloc サービス / 9タブUI。
- Pilot で `--demo` の全9タブ起動を確認。

### ハマりどころ

- slurmd 23.11 は `CgroupPlugin=disabled` が無く、cgroup v2 の初期化が必須。コンテナでは
  `privileged` + `cgroup: private` + 起動時に `/sys/fs/cgroup` のプロセスを子 cgroup へ退避し
  コントローラを委譲する必要があった。
- さらに slurmstepd は `/proc/1/cgroup` からルートを求めるため、slurmd が PID 1 だとパスが二重になり
  起動失敗する（`.../slurmstepd.scope/system.slice/...`）。compose で `init: true` にして解決。
- 数だけの GRES（File なし）は slurmd が 0 と報告し `inval` になる。`mknod` で偽 `/dev/nvidia[0-1]` を作成。
- `squeue -o` を `|` 区切りにすると、ジョブ名に `|` を含む場合に列がずれる（実機で再現）。
  区切りを ASCII Unit Separator（0x1f）にし、ジョブ名を最後の列にして maxsplit で保護。
- `SQUEUE_FORMAT` などの環境変数で出力形式が変わるため、コマンド実行時の環境から除去する。

### 判断

- ノード・GPU は `sinfo --json`（パーティション×状態の集約で、ノード単位の GRES 割当が取れない）ではなく
  `scontrol show node -o`（全バージョンで利用可、AllocTRES/Gres あり）を一次ソースにした。
- `AllocTRES` が出力に無いノードは割当不明（None）とし、空き GPU を推測しない。
- デモデータも Slurm 実出力形式で書き、本番と同じパーサーで読む（パーサーの回帰確認を兼ねる）。

### 続き（同日）

- 単体・UIテスト 127件（Pilot で9タブ、キー操作、デモでのキャンセル非実行、readonly、投入フォーム保存）。
- Docker の実Slurmで結合テスト 12件: capability検出、ノード/パーティション/spart、
  sbatch→squeue→ログ→scancel→sacct、GPU割当、他ユーザーのジョブのキャンセル拒否、sbatchエラー表示、
  --test-only、テキスト形式フォールバック、module、TUI起動、$JOBDIR ステージング copy-back、salloc。
- README / docs/usage.md / docs/hakusan-site.md / docs/development.md を作成。

### ハマりどころ（続き）

- **実バグ**: `asyncio.StreamReader.read(n)` は n バイト揃う前に返るため、コマンド出力が約40KBで切れていた。
  `squeue --json` が大きくなった時点で JSON 解析失敗→テキストへ誤フォールバックしたことで発覚。EOF までループして読むよう修正し回帰テストを追加。
- テスト用 `$JOBDIR` は Prolog（作成）/ TaskProlog（`export JOBDIR=`）/ Epilog（削除）で模倣。
- 一度、最終確認コマンドがプロセス強制終了（exit 137）したが、再実行で単体127件・結合12件とも成功。
