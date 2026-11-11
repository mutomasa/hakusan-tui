# HAKUSAN 実機確認待ちの項目

開発は Docker 上の Slurm 23.11.4 テストクラスタ（`docker/`）と、そこで採取した出力
（`tests/fixtures/slurm-23.11/`）で行った。HAKUSAN 実機では未確認のため、以下は **推測で確定していない**。

| # | 項目 | 現在の実装 | 実機で確認すること |
|---|---|---|---|
| 1 | Slurm バージョン・`--json` | 起動時に `squeue --json --me` を試し、失敗/解析不能ならテキスト形式（0x1f 区切り）。全ジョブの JSON が読めない場合も原因付きで警告して切替 | **実機で全ジョブの `squeue --json` が解析失敗（Expecting ',' delimiter）。出力サイズ・エラー位置を確認中**。資料記載 25.05.5 のスキーマと速度 |
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
| 14 | インストール方式 | uv の単体バイナリを `~/.local/bin` に置き、`uv tool install` で独立環境に導入（README）。HAKUSAN には venv も uv も無い前提。Singularity は使わない | ログインノードから GitHub / PyPI / python-build-standalone に出られるか（プロキシ設定の要否） |
| 15 | Python | uv が Python 3.12 を自動取得。代替としてサイト提供の Python（`module avail python`）を `--python` で指定 | 3.11 以上がサイト提供されているか。uv 取得版の Python がログインノードで動くか |
| 16 | ホーム容量・配置 | uv・Python・環境で約150MB。キャッシュは `uv cache clean` で削除 | ホームの quota。`~/.local` に置くことがサイト規則に反しないか |

## インストールの確認手順

1. README の「0. 事前確認」で、外部ネットワークに出られるか・ホームの容量・`module avail python` を確認して記録。
2. uv の tar.gz の `sha256sum -c` が OK になることを確認。
3. `uv tool install` 後に `hakusan-tui --diagnose` を実行し、Slurm / squeue --json / sacct / spart / module の結果を記録。
4. 外に出られない場合は、持ち込み方式（scp）とサイト提供 Python の組み合わせを試し、手順を README に反映する。

## 実機での受け入れ手順（Phase 4）

1. `hakusan-tui --diagnose` の結果を記録。
2. 小さな CPU ジョブで「投入 → 待機 → 実行 → 完了 → 履歴 → ログ」を確認。
3. 別のテストジョブで「キャンセル」を確認。他ユーザーのジョブに操作ボタンが出ないこと。
4. GPU タブの総数がサイト構成（A40 各2、A100 各2 など）と一致し、重複集計がないこと。
5. `spart` 解析結果と原文が一致すること。
6. 80×24 端末・SSH 遅延・No Color（`NO_COLOR=1`）で表示を確認。
