# 使い方

## 典型的な流れ

1. `ssh <ユーザー名>@hakusan1` でログインし、`uv run hakusan-tui` を起動。
2. `1` 概要でクラスタと自分のジョブの状況を確認。`4` GPU で型別の割当状況を確認。
3. `6` ジョブ投入でテンプレートを選択 → フォームに入力 → 右側の検証結果を確認。
4. 「保存」（`~/slurm_jobs/<ジョブ名>/job.sh`）→「投入…」→ 確認ダイアログで「投入する」。
5. `2` 自分のジョブで状態を確認。`Enter` で詳細とログ末尾、`c` でキャンセル。
6. 終了後は `7` 履歴で経過時間・割当資源・MaxRSS を確認。

## 各タブ

| タブ | 内容 | 主なコマンド |
|---|---|---|
| 1 概要 | ジョブ件数、ノード状態、GPU割当、待機/終了ジョブ上位5件 | 共通キャッシュのみ |
| 2 自分のジョブ | フィルタ・検索、詳細、ログ、キャンセル | `squeue`, `scontrol show job`, `sstat`, `scancel` |
| 3 キュー | 公開範囲の全ジョブ、パーティション別集計、待機理由、Slurm推定開始 | `squeue`, `squeue --start` |
| 4 GPU | 型別集計、GPUノード一覧、割当ジョブ | `scontrol show node -o` |
| 5 ノード | ノード一覧 / パーティション一覧 / 制限比較（spart） | `scontrol`, `spart` |
| 6 ジョブ投入 | テンプレート、フォーム、検証、保存、`sbatch`、`--test-only`、既存スクリプト投入 | `sbatch --parsable` |
| 7 履歴 | sacct（24時間/7日/30日）、ステップ階層、要求と実績、ログ探索 | `sacct` |
| 8 ツール | Module、対話ジョブ（salloc）、ステージング、PBS互換、環境診断 | `module`, `salloc` |
| 9 ヘルプ | はじめての方、用語、資料ページ対応、キー操作 | — |

## テンプレート

CPUシングル / CPUマルチコア / MPI / CPUでのコンパイルと実行 / CUDAコンパイルと実行 / Python AI学習 /
高速ストレージ使用（`$JOBDIR` ステージング）。モジュール名はサイトごとに違うため、テンプレートには
書き込みません。ツール > Module で選んで追加してください。

## 対話ジョブ

ツール > 対話ジョブで資源を指定 → コマンドを確認して開始。端末が対話セッションに切り替わります。
`hostname` で計算ノードにいるか確認し、終わったら `exit` で割当を解放して TUI に戻ります。

## 設定ファイル例

`~/.config/hakusan-tui/config.toml`

```toml
[ui]
default_tab = "dashboard"   # 起動時のタブ（dashboard / my_jobs / queue / gpu / ...）

[cluster]
profile = "hakusan"

[refresh]
jobs_seconds = 15
nodes_seconds = 30
history_seconds = 60

[safety]
read_only = false

[history]
default_days = 7
max_records = 500
```
