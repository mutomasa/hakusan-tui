# HAKUSAN 実機確認待ちの項目

開発は Docker 上の Slurm 23.11.4 テストクラスタ（`docker/`）と、そこで採取した出力
（`tests/fixtures/slurm-23.11/`）で行った。HAKUSAN 実機では未確認のため、以下は **推測で確定していない**。

| # | 項目 | 現在の実装 | 実機で確認すること |
|---|---|---|---|
| 1 | Slurm バージョン・`--json` | 起動時に `squeue --json --me` を試し、失敗/解析不能ならテキスト形式（0x1f 区切り） | 資料記載 25.05.5 での `squeue --json` スキーマ（data_parser v0.0.4x）と速度・出力サイズ |
| 2 | `spart` の書式 | 2行ヘッダー＋列数が揃った表なら解析、ダメなら原文表示。テストはスタブ（`docker/bin/spart`） | 実際の列（ユーザー上限、GPU列の有無）、`spart -l` 等のオプション |
| 3 | GPU の GRES 表記 | `Gres=gpu:<type>:<n>`、`AllocTRES` の `gres/gpu` / `gres/gpu:<type>`、`GresUsed`（あれば優先） | A40 / A100 / H100 VM の type 名。H100 1/4 の表現（現在は type 名に `1_4`/`vgpu`/`frac` 等を含むと「仮想/分割GPU」扱い） |
| 4 | GPU 使用率 accounting | 未実装（「取得不可」表示） | `AccountingStorageTRES` に `gres/gpuutil`・`gres/gpumem` があるか |
| 5 | `module` | `bash -lc 'module -t avail'`（Lmod 想定、テストは Lmod 8） | Environment Modules か Lmod か、初期化方法、実際のモジュール名 |
| 6 | `salloc` 後のシェル | `salloc` をそのまま端末占有で実行（テストではログインノード側でシェルが開き `srun` で計算ノード実行） | `LaunchParameters=use_interactive_step` 等で計算ノードのシェルになるか |
| 7 | `sacct` | `-S now-<N>days -u $USER`、0x1f 区切り、JobName を最後の列 | 収集遅延・保存期間、`MaxRSS` の反映タイミング |
| 8 | ログの場所・権限 | `scontrol show job` の `StdOut/StdErr` を読む（通常ファイル・読み取り可・末尾1MiB） | 計算ノードからの書き込み先が共有 `/home` か |
| 9 | `$JOBDIR` | `$JOBDIR` が無ければ即エラー終了するテンプレート。テストでは Prolog/TaskProlog/Epilog で模倣 | 実際の変数名・作成タイミング・容量・削除タイミング |
| 10 | PBS 互換ラッパー | `command -v` で検出し `qstat` / `pbsnodes -a` を読み取り表示のみ | 実際の設置場所とオプション対応状況 |
| 11 | パーティション別ルール | `scontrol` の MaxTime・ノード数・ノードの GPU 数・メモリで検証 | `--gres` 必須か、GPU パーティションの CPU/メモリ上限、ユーザー当たり同時実行数 |
| 12 | 対話ジョブ上限 | 資料の参考値（CPU 48h / GPU 12h）を説明文に表示するだけで判定に使わない | 現行ポリシー |
| 13 | ホスト名 | `hakusan1`/`hakusan2` なら「ログインノード」注意を表示（権限判定には使わない） | FQDN 表記 |

## 実機での受け入れ手順（Phase 4）

1. `hakusan-tui --diagnose` の結果を記録。
2. 小さな CPU ジョブで「投入 → 待機 → 実行 → 完了 → 履歴 → ログ」を確認。
3. 別のテストジョブで「キャンセル」を確認。他ユーザーのジョブに操作ボタンが出ないこと。
4. GPU タブの総数がサイト構成（A40 各2、A100 各2 など）と一致し、重複集計がないこと。
5. `spart` 解析結果と原文が一致すること。
6. 80×24 端末・SSH 遅延・No Color（`NO_COLOR=1`）で表示を確認。
