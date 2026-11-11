"""ヘルプタブ（はじめての方・用語・資料対応・コマンド早見表）。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Markdown

from hakusan_tui.screens.base import BaseTab

HELP_MD = """\
# はじめての方へ

> 資料: 「計算機講習会 [HAKUSAN]」Part 1（2026/4/14）。パーティション値などは当時の説明値で、
> 画面の値は必ず Slurm / `spart` から取得しています。

## 最初のジョブを投入する
1. `6` でジョブ投入タブへ。テンプレート「CPUシングル」を選ぶ。
2. パーティションと時間を指定し、右側の検証結果にエラーが無いことを確認。
3. 「保存」→「投入…」→ 確認ダイアログで「投入する」。
4. `2`（自分のジョブ）で状態を確認。`PD`=待機中、`R`=実行中。

## GPUを使う
- テンプレート「Python AI学習」または「CUDA」を選び、GPU数を指定（`--gres=gpu:N`）。
- `4`（GPU）で型別の **割当状況** を確認できます（実使用率ではありません）。

## 待機中の理由を見る
- 自分のジョブ/キューで行を選ぶと下部に待機理由の説明が出ます。
  - `Resources`: 資源が空くのを待っている / `Priority`: 優先度の高いジョブが先
  - `Dependency`: 依存ジョブ待ち / `QOS*`・`Assoc*`: 上限・ポリシー関連

## ログを読む
- 自分のジョブで `Enter` → 詳細ダイアログでログ末尾（`l` 再読込、`e` stdout/stderr 切替）。
- 出力ファイル名の `%x` はジョブ名、`%j` はジョブIDに置き換わります（資料 p.41）。

## ジョブを終了する
- 自分のジョブで `c` → 確認ダイアログで `scancel` の内容を確認して実行。
- 対話ジョブはシェルで `exit`。

## 用語
| 用語 | 意味 |
|---|---|
| Slurm | ジョブスケジューラ |
| パーティション | ジョブを投入するキュー（資源・時間の上限が違う） |
| ノード / ジョブ / タスク | 計算機1台 / 投入単位 / プロセス（`-n`） |
| GRES / TRES | 汎用資源（GPU等）/ 資源の種類と量（cpu, mem, gres/gpu） |
| MIG | GPUを分割したインスタンス。物理GPU枚数とは別 |
| PENDING / RUNNING | 待機中 / 実行中 |
| DRAIN | ノードが新規ジョブ受付を停止中 |
| CPUメモリ / VRAM | ノードのメモリ / GPUのメモリ |
| `$JOBDIR` | ジョブごとの高速作業領域。ジョブ終了で削除 |

## 画面と資料ページ
| 画面 | 主なコマンド | 資料 |
|---|---|---|
| 概要・ノード | sinfo / scontrol / spart | p.5–14, 38–39 |
| 自分のジョブ・キュー | squeue / scancel | p.47–49 |
| ジョブ投入 | sbatch / #SBATCH | p.40–45 |
| 履歴 | sacct | p.46 |
| ツール | module / salloc / $JOBDIR / PBS | p.27–30, 34, 43, 50–52, 56 |

## キー操作
`1`〜`9` タブ切替 / `Enter` 詳細 / `Esc` 閉じる / `/` 検索 / `r` 更新 / `s` 投入 / `c` キャンセル /
`?` この画面の説明 / `q` 終了

## 参考リンク
- Slurm: https://slurm.schedmd.com/ （squeue, sbatch, sacct, scancel, salloc, gres）
- JAIST パーティション参考: https://www.jaist.ac.jp/iscenter/mpc/kagayaki/2/#c5869
"""


class HelpTab(BaseTab):
    HELP_TITLE = "ヘルプ"
    HELP_TEXT = "はじめての方向けのガイドと用語集です。"

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Markdown(HELP_MD)
