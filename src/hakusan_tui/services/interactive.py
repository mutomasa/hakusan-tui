"""対話ジョブ（salloc）。端末を一時的に対話セッションへ渡すため ``App.suspend()`` 中に実行する。"""

from __future__ import annotations

import contextlib
import shlex
import subprocess
from dataclasses import dataclass

from hakusan_tui.adapters.slurm_parsers import parse_duration
from hakusan_tui.services.command_runner import build_environment
from hakusan_tui.validation import MEMORY_RE, is_partition


@dataclass(frozen=True)
class InteractiveRequest:
    partition: str = ""
    ntasks: str = "1"
    cpus_per_task: str = ""
    mem: str = ""
    gpus: str = ""
    time: str = "01:00:00"


def build_salloc_argv(req: InteractiveRequest) -> list[str]:
    """検証済みの値から salloc の引数配列を組み立てる。不正値は ValueError。"""
    _validate(req)
    argv = ["salloc"]
    if req.partition:
        argv += ["-p", req.partition]
    if req.ntasks:
        argv += ["-n", req.ntasks]
    if req.cpus_per_task:
        argv += ["--cpus-per-task", req.cpus_per_task]
    if req.mem:
        argv += ["--mem", req.mem]
    if req.gpus and req.gpus != "0":
        argv += ["--gres", f"gpu:{req.gpus}"]
    if req.time:
        argv += ["--time", req.time]
    return argv


def _validate(req: InteractiveRequest) -> None:
    if req.partition and not is_partition(req.partition):
        raise ValueError("パーティション名が不正です")
    for name in ("ntasks", "cpus_per_task", "gpus"):
        value = getattr(req, name)
        if value and not value.isdigit():
            raise ValueError(f"{name} は整数で指定してください")
    if req.mem and not MEMORY_RE.fullmatch(req.mem):
        raise ValueError("メモリは 8G のように指定してください")
    if req.time and parse_duration(req.time) is None:
        raise ValueError("時間は HH:MM:SS で指定してください")


def preview(argv: list[str]) -> str:
    return " ".join(shlex.quote(a) for a in argv)


BANNER = """
==================== hakusan-tui: 対話ジョブ ====================
割当が始まるとシェルが開きます（サイト設定により計算ノードまたはログインノード上）。
  - 計算ノードにいるか確認:  hostname
  - 割当内でコマンド実行:      srun <command>（サイトのガイドに従う）
  - 終了して TUI に戻る:       exit   （割当が解放されます）
待機中に中断する場合は Ctrl+C。
=================================================================
"""


def run_interactive(argv: list[str]) -> int:
    """端末占有で salloc を実行する（App.suspend() の中から呼ぶ）。"""
    print(BANNER)
    print("実行:", preview(argv), flush=True)
    try:
        completed = subprocess.run(argv, env=build_environment(), check=False)
    except FileNotFoundError:
        print("salloc が見つかりません")
        return 127
    except KeyboardInterrupt:
        return 130
    print(f"\n対話ジョブが終了しました（終了コード {completed.returncode}）。Enter で TUI に戻ります。")
    with contextlib.suppress(EOFError, KeyboardInterrupt):
        input()
    return completed.returncode
