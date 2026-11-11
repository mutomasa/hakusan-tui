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

### インストール手順の見直し（同日）

- HAKUSAN には venv も uv も無く、Singularity がある、との情報を受けて README を書き直した。
  uv の単体バイナリ（musl 版、sha256 を確認）を `~/.local/bin` に置き、`uv tool install` で入れる方式。
- Singularity は Slurm CLI・`/etc/slurm`・munge をバインドする必要があり壊れやすいので使わない、と明記。
- 手元で GitHub から `uv tool install` → `hakusan-tui --demo --diagnose` が動き、
  wheel に `app.tcss` とデモデータが含まれることを確認。uv 0.7.9 musl 版の配布 URL も存在を確認。
- 実機未確認の項目（外部ネットワーク、Python、quota）を `docs/hakusan-site.md` の #14〜#16 に追加。

## 2026-11-12

### やったこと

- HAKUSAN 実機で「JSON解析に失敗したためテキスト形式に切替: Expecting ',' delimiter」が出たと報告を受けた。
  起動時の判定（`squeue --json --me`）は通り、全ジョブの `squeue --json` で失敗している。
- 原因候補: (1) 出力上限 16MiB での切り詰め、(2) Slurm の JSON 自体が不正（特殊文字のエスケープ不備など）。未特定。
- 警告文に原因（切り詰めか不正JSONか）・バイト数・エラー位置を出すよう変更。出力内容は含めない（他人のジョブ名が出るため）。
- `--diagnose` に「ジョブ一覧の取得」（全ジョブを実際に取得して JSON のまま読めたか）を追加。
- `squeue --json` のタイムアウトを 5 秒 → 15 秒に延長（全ジョブは大きいため）。
- テスト追加（壊れたJSON / 切り詰め）。単体・UI 129 件成功。Docker クラスタは停止中のため結合テストは未実行。

### 次にやること

- HAKUSAN で `squeue --json` の出力サイズとエラー位置を確認してもらい、原因に応じて対処
  （切り詰めなら上限・取得方法の見直し、不正 JSON なら Slurm 側の問題としてテキスト形式を既定に）。

### squeue --json 問題の原因と対処（同日）

- 新しい警告で原因が判明: **全ジョブの `squeue --json` が 16MiB を超えて切り詰められていた**（HAKUSAN 実機）。
- 上限を上げる案は不採用。15 秒ごとに数十MBの JSON をログインノードで取得・解析するのは重く、
  「ログインノードに負荷をかけない」方針に反する。
- 取得方式を変更: 全ジョブ = テキスト形式（0x1f 区切り、1件約100バイト）、自分のジョブ = `squeue --json --me`
  で詳細（ReqTRES・StdOut など）を取得し、テキスト結果の該当ジョブを置き換える（`merge_jobs`）。
  待機中の配列ジョブ（テキスト `123_[1-10]` と JSON `123`）は同一とみなし重複させない。
- 設計書 7.1 の「ジョブ一覧: `squeue --json` 一次候補」から外れるが、実機の規模による判断。
- 単体・UI 132 件、Docker 実Slurm 結合 12 件成功。

### PATH の永続化（同日）

- HAKUSAN 実機で再ログイン後に `uv` が見つからなくなった（`Command 'uv' not found ... snap install astral-uv`）。
  README の手順が `~/.bashrc` だけに PATH を追記しており、ログインシェルが読む `~/.bash_profile` / `~/.profile` に無かったのが原因と推定。
- README の手順2を、`~/.bash_profile`・`~/.profile`・`~/.bashrc` に重複なく追記する形に修正。zsh / tcsh の注記を追加。
  仮のホームで3パターン（なし / .profile のみ / 両方あり）と2回実行で重複しないことを確認。

### バージョン表示（同日）

- 画面右上にバージョンをセマンティック形式（`v0.1.1`）で表示。バージョンを 0.1.0 → **0.1.1** に更新。
- バージョンの定義を `src/hakusan_tui/__init__.py` の `__version__` だけにした（pyproject は hatch の dynamic version で読む）。
  `hakusan-tui --version` とパッケージのメタデータも同じ値になることをテストで確認。
- 80桁端末ではバージョン表示に押されて末尾の「デモ / 読取専用」が切れていたため、モード表示を先頭（`HAKUSAN [デモ]`）に移動。
  代わりに 80桁では末尾の「接続: 正常」が切れることがある（実機はホスト名が短いので余裕は増える）。
- 単体・UI 135 件成功。

## 2026-11-12

### 汎用化（v0.2.0）

- HAKUSAN 以外の Slurm クラスタでも使えるよう、サイト依存の判定を減らした。
- パーティションの CPU/GPU/VM 判定を名前（`GPU` で始まる）から、所属ノードの GRES とパーティションの TRES に変更。
  名前は構成から判断できないときの手がかりにだけ使う。`a100q` のような名前の GPU パーティションで
  「CPUパーティションのようです」と誤警告していた問題がなくなる。判定は `adapters/classify.py` に分離（`hakusan.py` は spart とログインノード名だけ）。
- GPU の型見出しは A40/A100/H100 以外を「その他」にまとめていたのを、Slurm の type 名（`V100` など）に変更。
  MIG・分割GPUは見出しに単位を付け、物理GPUと混ざらないようにした。
- `--diagnose` のホスト名表示を HAKUSAN 固有の文言から一般的な文言に変更。
- `$JOBDIR` テンプレートとヘルプ文は HAKUSAN 向けのまま（`--profile` での切替は残課題）。
- バージョンを 0.2.0 に更新（機能追加のためマイナーを上げた）。

