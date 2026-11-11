"""読み取り専用ツールコマンドのホワイトリスト（module / PBS互換 / 診断）。

``module`` はシェル関数なので ``bash -lc`` を使う。スクリプト本体は固定文字列で、
利用者が選んだモジュール名は位置引数 ``$1`` として渡し、文字列連結しない。
"""

from __future__ import annotations

from collections.abc import Callable

from hakusan_tui.validation import is_job_id, is_module_name

PBS_COMMANDS = ("qsub", "qstat", "qdel", "qalter", "qhold", "qrls", "qrerun", "pbsnodes")


def _module_avail(_args: tuple[str, ...]) -> list[str]:
    return ["bash", "-lc", "module -t avail 2>&1"]


def _module_list(_args: tuple[str, ...]) -> list[str]:
    return ["bash", "-lc", "module -t list 2>&1"]


def _module_show(args: tuple[str, ...]) -> list[str]:
    if len(args) != 1 or not is_module_name(args[0]):
        raise ValueError("モジュール名が不正です")
    return ["bash", "-lc", 'module show "$1" 2>&1', "bash", args[0]]


def _module_which(args: tuple[str, ...]) -> list[str]:
    """モジュール適用済みの一時シェルでコンパイラ等の場所を調べる（読み取り診断）。"""
    if not all(is_module_name(a) for a in args):
        raise ValueError("モジュール名が不正です")
    script = (
        'for m in "$@"; do module load "$m" 2>&1; done; '
        "for c in gcc g++ gfortran icx icpx ifx mpicc mpiicx nvcc; do "
        'printf "%s: %s\\n" "$c" "$(command -v "$c" || echo なし)"; done'
    )
    return ["bash", "-lc", script, "bash", *args]


def _qstat(_args: tuple[str, ...]) -> list[str]:
    return ["qstat"]


def _pbsnodes(_args: tuple[str, ...]) -> list[str]:
    return ["pbsnodes", "-a"]


def _sstat(args: tuple[str, ...]) -> list[str]:
    if len(args) != 1 or not is_job_id(args[0]):
        raise ValueError("ジョブIDが不正です")
    return ["sstat", "-j", args[0], "-n", "-P",
            "--format=JobID,AveCPU,AveRSS,MaxRSS,MaxVMSize,NTasks"]


READONLY_TOOLS: dict[str, Callable[[tuple[str, ...]], list[str]]] = {
    "module_avail": _module_avail,
    "module_list": _module_list,
    "module_show": _module_show,
    "module_which": _module_which,
    "qstat": _qstat,
    "pbsnodes": _pbsnodes,
    "sstat": _sstat,
}


def build_tool_argv(name: str, args: tuple[str, ...] = ()) -> list[str]:
    builder = READONLY_TOOLS.get(name)
    if builder is None:
        raise ValueError(f"未登録のツールです: {name}")
    return builder(args)


def parse_module_terse(text: str) -> list[str]:
    """``module -t avail`` の出力からモジュール名一覧を取り出す（見出し行は除外）。"""
    names = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.endswith(":") or line.startswith(("-", "No module")):
            continue
        names.append(line.removesuffix("(default)").strip())
    return names
