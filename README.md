# hakusan-tui

JAIST HAKUSAN（Slurm）を初めて使う人のための、Slurm / GPU / ジョブをまとめて扱うターミナルUIです。
Python + [Textual](https://textual.textualize.io/) 製。仕様は [`docs/slurm.md`](docs/slurm.md)。

- 待機中（PD）・実行中（R）を日本語で表示し、待機理由（Resources / Priority など）を説明します。
- GPU は **Slurm上の割当数** を型別（A40 / A100 / H100 VM）に表示します。実使用率とは区別し、
  取得できない値を 0 や推測値で埋めません。
- ジョブ投入はフォーム → スクリプト全文プレビュー → 保存 → 確認して `sbatch`。
- キャンセルは自分のジョブだけ、実行直前の所有者再確認と二段階確認の後に `scancel`。

## インストール

```bash
# HAKUSAN ログインノード上で（資料 p.18: ssh <ユーザー名>@hakusan1）
git clone <this repo> hakusan-tui && cd hakusan-tui
uv sync
uv run hakusan-tui
```

Python 3.11 以上と [uv](https://docs.astral.sh/uv/) が必要です。管理者権限・常駐サーバは不要で、
SSH のパスワードや鍵は扱いません。

## 起動オプション

```bash
hakusan-tui                 # 通常起動（ログインノード上の Slurm CLI を使用）
hakusan-tui --demo          # Slurm なしでサンプルデータを表示（コマンドは一切実行しない）
hakusan-tui --readonly      # 閲覧専用（投入・キャンセル・対話ジョブを無効化）
hakusan-tui --diagnose      # 軽量な環境診断を表示して終了
hakusan-tui --profile hakusan
hakusan-tui --version
```

## キー操作

| キー | 動作 |
|---|---|
| `1`〜`9` | タブ切替（概要 / 自分のジョブ / キュー / GPU / ノード / ジョブ投入 / 履歴 / ツール / ヘルプ） |
| `Enter` | 詳細（ジョブ詳細ではログ末尾も表示） |
| `Esc` | ダイアログを閉じる |
| `/` | 検索欄へ |
| `r` | 現在のタブを更新（短いクールダウンあり） |
| `s` | ジョブ投入タブへ |
| `c` | 自分のジョブで選択中のジョブをキャンセル（確認あり） |
| `?` | その画面の説明 |
| `q` | 終了（未保存のフォームがあれば確認。バッチジョブは止まりません） |

入力欄にフォーカスがある間は、数字や `q` などは文字として入力されます。

## 設定

`~/.config/hakusan-tui/config.toml`（例は `docs/usage.md`）。更新間隔・読み取り専用・履歴期間などを変更できます。

## FAQ

- **GPU の「未割当」があるのに投入しても待たされる** — 未割当は Slurm 上の値で、パーティション・QOS・
  ユーザー上限などにより必ず使えるとは限りません。
- **GPU 使用率が「取得不可」** — 自動収集は OFF です。ログインノードから `nvidia-smi` を連続実行しません。
- **`module load` しても反映されない** — `module` はシェル関数で、TUI からは今のシェルに引き継げません。
  ツール > Module で選び、「投入フォームに追加」でジョブスクリプトに書き込みます。
- **ログが表示されない** — 待機中でまだファイルが無いか、出力先が別の場所です。他ユーザーのログは表示しません。

## 制限事項

- PBS 互換の変更系（`qalter` / `qhold` / `qrls` / `qrerun`）は案内のみで、TUI からは実行しません。
- GPU 実機メトリクス（利用率・VRAM・温度）は未実装（取得不可と表示）。
- コンテナ実行・Jupyter・conda 環境作成は対象外（講習資料 Part 2/3 の範囲）。
- HAKUSAN 実機での確認が必要な項目は [`docs/hakusan-site.md`](docs/hakusan-site.md) を参照。

## 開発

[`docs/development.md`](docs/development.md) を参照。Docker 上の Slurm クラスタで結合テストを行えます。

```bash
uv run pytest -q
uv run ruff check .
```

## 出典

「計算機講習会 [HAKUSAN]」株式会社HPCソリューションズ、2026/4/14、Part 1（58ページ）。
資料の数値（パーティション上限・ノード台数）は説明時点の値で、本ツールは画面表示・判定に必ず Slurm /
`spart` の現在値を使います。
