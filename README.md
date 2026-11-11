# hakusan-tui

JAIST HAKUSAN（Slurm）を初めて使う人のための、Slurm / GPU / ジョブをまとめて扱うターミナルUIです。
Python + [Textual](https://textual.textualize.io/) 製。仕様は [`docs/slurm.md`](docs/slurm.md)。

## スクリーンショット
<img width="789" height="856" alt="image" src="https://github.com/user-attachments/assets/32e91879-336a-4e58-8a46-ca18e12b90d7" />


- 待機中（PD）・実行中（R）を日本語で表示し、待機理由（Resources / Priority など）を説明します。
- GPU は **Slurm上の割当数** を型別（A40 / A100 / H100 VM）に表示します。実使用率とは区別し、
  取得できない値を 0 や推測値で埋めません。
- ジョブ投入はフォーム → スクリプト全文プレビュー → 保存 → 確認して `sbatch`。
- キャンセルは自分のジョブだけ、実行直前の所有者再確認と二段階確認の後に `scancel`。

## インストール（HAKUSAN の個人ホームへ）

HAKUSAN には Python の venv も uv もないため、**uv の単体バイナリをホームに置き、uv が管理する
Python で独立した環境にインストール** します。root もシステムの Python も不要で、すべて `~/.local`
の下に収まります。管理者権限・常駐サーバは使わず、SSH のパスワードや鍵も扱いません。

> HAKUSAN 実機での手順確認はまだです（[`docs/hakusan-site.md`](docs/hakusan-site.md) の #14〜#16）。

### 0. 事前確認

```bash
ssh <JAISTユーザー名>@hakusan1         # 資料 p.18
curl -sI https://pypi.org | head -1    # ログインノードから外に出られるか
quota -s 2>/dev/null || df -h ~        # ホームの容量（全体で約150MB使います）
module avail python 2>&1 | head        # サイト提供の Python 3.11 以上があるか（任意）
```

### 1. uv をホームに置く

`curl | sh` は使わず、チェックサムを確認してから展開します。

```bash
VER=0.7.9    # 最新版を使う場合は https://github.com/astral-sh/uv/releases で確認
ARCH=x86_64-unknown-linux-musl   # 静的リンク版。古い glibc でも動く
mkdir -p ~/.local/bin ~/tmp/uv-dl && cd ~/tmp/uv-dl
curl -fLO https://github.com/astral-sh/uv/releases/download/$VER/uv-$ARCH.tar.gz
curl -fLO https://github.com/astral-sh/uv/releases/download/$VER/uv-$ARCH.tar.gz.sha256
sha256sum -c uv-$ARCH.tar.gz.sha256          # OK と出ることを確認
tar xzf uv-$ARCH.tar.gz
install -m 755 uv-$ARCH/uv uv-$ARCH/uvx ~/.local/bin/
cd ~ && rm -rf ~/tmp/uv-dl
```

### 2. PATH を通す

ログインしたときに読まれるのは `~/.bash_profile` / `~/.profile` で、`~/.bashrc` だけに書くと
**再ログイン後に `uv` が見つからなくなる** ことがあります（HAKUSAN 実機で発生）。両方に書きます。

```bash
echo $SHELL                                   # bash 以外なら下の注記を参照
LINE='export PATH="$HOME/.local/bin:$PATH"'
# ログインシェル用（~/.bash_profile があると bash は ~/.profile を読まないので両方確認）
for f in ~/.bash_profile ~/.profile; do
  [ -f "$f" ] && ! grep -q 'HOME/.local/bin' "$f" && echo "$LINE" >> "$f"
done
[ -f ~/.bash_profile ] || [ -f ~/.profile ] || echo "$LINE" > ~/.profile
# 対話シェル用
grep -q 'HOME/.local/bin' ~/.bashrc 2>/dev/null || echo "$LINE" >> ~/.bashrc

export PATH="$HOME/.local/bin:$PATH"          # 今のセッションにも反映
uv --version
```

- zsh の場合は `~/.zshrc` に同じ `export` 行を、tcsh/csh の場合は `~/.cshrc` に
  `setenv PATH $HOME/.local/bin:$PATH` を書きます。
- 一度ログアウトして入り直し、`uv --version` が動くことを確認してください。
- `Command 'uv' not found ... snap install astral-uv` と出るのは PATH が通っていないときの Ubuntu の案内です
  （snap は root が必要なので使いません）。`ls ~/.local/bin/uv` でファイルがあれば、上の設定だけで直ります。

### 3. hakusan-tui をインストール

```bash
# Python 3.12 は uv が自動で取得する（システムの Python は変更しない）
uv tool install --python 3.12 git+https://github.com/mutomasa/hakusan-tui
# git が無い場合
uv tool install --python 3.12 https://github.com/mutomasa/hakusan-tui/archive/refs/heads/main.zip
# サイト提供の Python 3.11 以上を使う場合（Python のダウンロードを省ける）
uv tool install --python "$(which python3)" git+https://github.com/mutomasa/hakusan-tui

uv cache clean               # ダウンロードキャッシュ（~/.cache/uv）を消して容量を節約
hakusan-tui --diagnose       # 動作確認
hakusan-tui
```

### 入る場所・更新・削除

| もの | 場所 |
|---|---|
| uv / uvx | `~/.local/bin/` |
| Python | `~/.local/share/uv/python/` |
| hakusan-tui の環境 | `~/.local/share/uv/tools/hakusan-tui/`（コマンドは `~/.local/bin/hakusan-tui`） |
| 設定 | `~/.config/hakusan-tui/config.toml` |

```bash
uv tool upgrade hakusan-tui      # 更新
uv tool uninstall hakusan-tui    # 削除
rm -f ~/.local/bin/uv ~/.local/bin/uvx && rm -rf ~/.local/share/uv ~/.cache/uv   # uv ごと削除
```

### ログインノードから外に出られない場合

手元の PC で uv の tar.gz を用意して `scp` で持ち込みます。Python とパッケージもダウンロードが必要なので、
サイト提供の Python 3.11 以上（`module`）を使うか、手元で依存込みのファイルを作って持ち込む必要があります。

### Singularity を使わない理由

このTUIはログインノードの `squeue`・`sbatch`・`scancel`・`sacct` を直接呼びます。コンテナ内から使うには
Slurm のコマンドとライブラリ、`/etc/slurm`、munge のソケットをすべてバインドする必要があり、壊れやすく、
サイトのバージョンとずれる危険があります。Singularity は計算ノード上のジョブ（学習など）に使ってください。

### 開発環境（手元の PC）

```bash
git clone https://github.com/mutomasa/hakusan-tui && cd hakusan-tui
uv sync
uv run hakusan-tui --demo    # Slurm がなくてもサンプルデータで体験できる
```

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
