"""ジョブスクリプトの生成・検証・保存。

- サイトの既定値を推測して暗黙に使わない。未指定は「クラスタ既定を使用」。
- ``#SBATCH`` 行に改行・制御文字を入れさせない（ヘッダー注入防止）。
- 保存は既存ファイルを無断で上書きしない。保存するまで投入しない。
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field, replace
from pathlib import Path

from hakusan_tui.adapters.gpu import parse_gres
from hakusan_tui.adapters.hakusan import partition_kind
from hakusan_tui.adapters.slurm_parsers import format_duration, parse_duration, parse_memory_mib
from hakusan_tui.models import Node, Partition
from hakusan_tui.validation import (
    EMAIL_RE,
    GPU_TYPE_RE,
    JOB_NAME_RE,
    MAIL_TYPES,
    MEMORY_RE,
    OUTPUT_PATH_RE,
    has_control_chars,
    is_module_name,
    is_partition,
)

DEFAULT_JOBS_DIR = "~/slurm_jobs"


@dataclass(frozen=True)
class JobSpec:
    template: str = "cpu_single"
    job_name: str = "my_job"
    partition: str = ""
    nodes: str = ""
    ntasks: str = ""
    cpus_per_task: str = ""
    mem: str = ""
    gpus: str = ""
    gpu_type: str = ""
    time: str = ""
    output: str = "%x-%j.out"
    error: str = "%x-%j.err"
    mail_type: str = ""
    mail_user: str = ""
    modules: tuple[str, ...] = ()
    command: str = ""
    use_staging: bool = False
    stage_in: tuple[str, ...] = ()
    stage_out: tuple[str, ...] = ()


@dataclass(frozen=True)
class Issue:
    level: str  # error / warning / info
    field: str
    message: str


@dataclass(frozen=True)
class Template:
    key: str
    label: str
    description: str
    overrides: dict[str, object] = field(default_factory=dict)


TEMPLATES: dict[str, Template] = {
    t.key: t
    for t in (
        Template("cpu_single", "CPUシングル", "1タスク・1コアの基本ジョブ（資料 p.40–42）",
                 {"ntasks": "1", "cpus_per_task": "1", "command": "./a.out"}),
        Template("cpu_multicore", "CPUマルチコア", "OpenMP等で1タスク複数コアを使う",
                 {"ntasks": "1", "cpus_per_task": "8",
                  "command": "export OMP_NUM_THREADS=\"$SLURM_CPUS_PER_TASK\"\n./a.out"}),
        Template("mpi", "MPI（単一/複数ノード）", "MPIで複数タスクを起動（資料 p.32–34, 53–54）",
                 {"nodes": "1", "ntasks": "4", "cpus_per_task": "1",
                  "command": "# サイト推奨のMPI起動方法を確認してください\nmpirun ./a.out"}),
        Template("cpu_compile", "CPUでのコンパイルと実行", "計算ノード上でコンパイルしてから実行",
                 {"ntasks": "1", "cpus_per_task": "1",
                  "command": "gcc -O2 -o hello hello.c\n./hello"}),
        Template("cuda_compile", "GPU上でのCUDAコンパイルと実行", "nvccでコンパイルしてGPUで実行",
                 {"ntasks": "1", "cpus_per_task": "4", "gpus": "1",
                  "command": "nvcc -O2 -o hello hello.cu\n./hello"}),
        Template("python_ai", "Python AI学習", "GPU 1枚でPython学習スクリプトを実行",
                 {"ntasks": "1", "cpus_per_task": "4", "gpus": "1", "mem": "32G",
                  "time": "02:00:00",
                  "command": "# 実行環境（venv/conda等）はジョブ内で準備してください\npython train.py"}),
        Template("staging", "高速ストレージ使用", "input→$JOBDIR→outputを戻す（資料 p.50–52）",
                 {"ntasks": "1", "cpus_per_task": "1", "use_staging": True,
                  "stage_in": ("input.dat",), "stage_out": ("result.dat",),
                  "command": "./a.out input.dat > result.dat"}),
    )
}


def apply_template(key: str, base: JobSpec | None = None) -> JobSpec:
    """テンプレートを適用する。ジョブ名・パーティション・通知設定だけ引き継ぐ。"""
    base = base or JobSpec()
    spec = JobSpec(
        template=key, job_name=base.job_name, partition=base.partition,
        mail_type=base.mail_type, mail_user=base.mail_user,
    )
    return replace(spec, **TEMPLATES[key].overrides)  # type: ignore[arg-type]


# ------------------------------------------------------------------ 検証


def validate(
    spec: JobSpec, partitions: list[Partition] | None = None, nodes: list[Node] | None = None
) -> list[Issue]:
    issues: list[Issue] = []
    issues += _check_header_safety(spec)
    issues += _check_basic_fields(spec)
    issues += _check_numbers(spec)
    issues += _check_mail(spec)
    issues += _check_modules_and_command(spec)
    issues += _check_partition(spec, partitions, nodes)
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.level == "error" for i in issues)


def _header_values(spec: JobSpec) -> dict[str, str]:
    return {
        "job_name": spec.job_name, "partition": spec.partition, "nodes": spec.nodes,
        "ntasks": spec.ntasks, "cpus_per_task": spec.cpus_per_task, "mem": spec.mem,
        "gpus": spec.gpus, "gpu_type": spec.gpu_type, "time": spec.time,
        "output": spec.output, "error": spec.error, "mail_type": spec.mail_type,
        "mail_user": spec.mail_user,
    }


def _check_header_safety(spec: JobSpec) -> list[Issue]:
    return [
        Issue("error", name, "改行・制御文字は使えません")
        for name, value in _header_values(spec).items()
        if has_control_chars(value)
    ]


def _check_basic_fields(spec: JobSpec) -> list[Issue]:
    issues = []
    if not JOB_NAME_RE.fullmatch(spec.job_name):
        issues.append(Issue("error", "job_name", "ジョブ名は英数字と _ . - のみ（128文字以内）"))
    if spec.partition and not is_partition(spec.partition):
        issues.append(Issue("error", "partition", "パーティション名が不正です"))
    for name in ("output", "error"):
        value = getattr(spec, name)
        if value and (not OUTPUT_PATH_RE.fullmatch(value) or ".." in value.split("/")):
            issues.append(Issue("error", name, "出力パスは英数字と _ . - / % ~ のみ（.. 不可）"))
    if spec.gpu_type and not GPU_TYPE_RE.fullmatch(spec.gpu_type):
        issues.append(Issue("error", "gpu_type", "GPUタイプ名が不正です"))
    return issues


def _check_numbers(spec: JobSpec) -> list[Issue]:
    issues = []
    for name in ("nodes", "ntasks", "cpus_per_task"):
        value = getattr(spec, name)
        if value and (not value.isdigit() or int(value) < 1):
            issues.append(Issue("error", name, "1以上の整数を入力してください"))
    if spec.gpus and not spec.gpus.isdigit():
        issues.append(Issue("error", "gpus", "GPU数は0以上の整数です"))
    if spec.mem and not MEMORY_RE.fullmatch(spec.mem):
        issues.append(Issue("error", "mem", "メモリは 32G / 4000M のように指定（単位 K/M/G/T）"))
    if spec.time and parse_duration(spec.time) is None:
        issues.append(Issue("error", "time", "時間は HH:MM:SS または D-HH:MM:SS で指定"))
    if spec.ntasks and spec.ntasks.isdigit() and int(spec.ntasks) > 1 and spec.template != "mpi":
        issues.append(Issue("info", "ntasks",
                            "--ntasks はプロセス数です。1プロセス多コアなら --cpus-per-task を使います"))
    if spec.nodes.isdigit() and int(spec.nodes) > 1:
        issues.append(Issue("warning", "nodes", "複数ノードではMPI等の通信方式が必要な場合があります"))
    return issues


def _check_mail(spec: JobSpec) -> list[Issue]:
    issues = []
    types = [t.strip() for t in spec.mail_type.split(",") if t.strip()]
    if any(t.upper() not in MAIL_TYPES for t in types):
        issues.append(Issue("error", "mail_type", f"使用できる値: {', '.join(MAIL_TYPES)}"))
    if spec.mail_user and not EMAIL_RE.fullmatch(spec.mail_user):
        issues.append(Issue("error", "mail_user", "メールアドレスの形式が不正です"))
    if types and not spec.mail_user:
        issues.append(Issue("info", "mail_user", "--mail-user 未指定時はサイト既定の宛先になります"))
    return issues


def _check_modules_and_command(spec: JobSpec) -> list[Issue]:
    issues = [
        Issue("error", "modules", f"モジュール名が不正です: {m!r}")
        for m in spec.modules
        if not is_module_name(m)
    ]
    if not spec.command.strip():
        issues.append(Issue("error", "command", "実行コマンドを入力してください（計算ノードで実行されます）"))
    for f in (*spec.stage_in, *spec.stage_out):
        if not f or has_control_chars(f) or f.startswith("/") or ".." in f.split("/"):
            issues.append(Issue("error", "staging", f"ステージング対象は相対パスで指定: {f!r}"))
    return issues


def _check_partition(
    spec: JobSpec, partitions: list[Partition] | None, nodes: list[Node] | None
) -> list[Issue]:
    if not spec.partition:
        return [Issue("info", "partition", "パーティション未指定: クラスタ既定を使用します")]
    if partitions is None:
        return [Issue("info", "partition", "パーティション情報を取得できていません（要確認）")]
    part = next((p for p in partitions if p.name == spec.partition), None)
    if part is None:
        return [Issue("error", "partition", f"現在のSlurmに存在しないパーティションです: {spec.partition}")]
    return _check_against_partition(spec, part, nodes or [])


def _check_against_partition(spec: JobSpec, part: Partition, nodes: list[Node]) -> list[Issue]:
    issues = []
    if part.available is False:
        issues.append(Issue("warning", "partition", f"{part.name} は現在 {part.state_summary} です"))
    issues += _check_time_limit(spec, part)
    if spec.nodes.isdigit() and part.total_nodes is not None and int(spec.nodes) > part.total_nodes:
        issues.append(Issue("error", "nodes", f"{part.name} のノード数 {part.total_nodes} を超えています"))
    issues += _check_gpu(spec, part, [n for n in nodes if n.name in set(part.node_names)])
    issues += _check_memory(spec, [n for n in nodes if n.name in set(part.node_names)])
    return issues


def _check_time_limit(spec: JobSpec, part: Partition) -> list[Issue]:
    requested = parse_duration(spec.time) if spec.time else None
    if requested is None:
        return []
    if part.max_time_seconds is None:
        return [Issue("info", "time", f"{part.name} の上限時間は取得できません（要確認）")]
    if requested > part.max_time_seconds:
        limit = format_duration(part.max_time_seconds)
        return [Issue("error", "time", f"{part.name} の上限 {limit} を超えています")]
    return []


def _max_gpus_per_node(nodes: list[Node]) -> int | None:
    counts = [sum(e.count or 0 for e in parse_gres(n.gres_raw) if e.name == "gpu") for n in nodes]
    return max(counts) if counts else None


def _check_gpu(spec: JobSpec, part: Partition, nodes: list[Node]) -> list[Issue]:
    gpus = int(spec.gpus) if spec.gpus.isdigit() else 0
    kind = partition_kind(part.name)
    if gpus == 0:
        return [Issue("warning", "gpus", "GPUパーティションですがGPUを要求していません")] if kind != "CPU" else []
    if kind == "CPU":
        return [Issue("warning", "gpus", f"{part.name} はCPUパーティションのようです")]
    max_gpus = _max_gpus_per_node(nodes)
    if max_gpus is None:
        return [Issue("info", "gpus", "ノードあたりのGPU数を確認できません（要確認）")]
    if gpus > max_gpus:
        return [Issue("error", "gpus", f"ノードあたりのGPUは最大 {max_gpus} です（Slurm上の構成）")]
    return []


def _check_memory(spec: JobSpec, nodes: list[Node]) -> list[Issue]:
    requested = parse_memory_mib(spec.mem) if spec.mem else None
    sizes = [n.memory_total_mib for n in nodes if n.memory_total_mib is not None]
    if requested is None or not sizes:
        return []
    if requested > max(sizes):
        return [Issue("error", "mem", f"ノードの搭載メモリ {max(sizes)} MiB を超えています")]
    return []


# ------------------------------------------------------------------ 生成


def gres_value(spec: JobSpec) -> str | None:
    if not spec.gpus.isdigit() or int(spec.gpus) == 0:
        return None
    return f"gpu:{spec.gpu_type}:{spec.gpus}" if spec.gpu_type else f"gpu:{spec.gpus}"


def sbatch_directives(spec: JobSpec) -> list[str]:
    options = [
        ("job-name", spec.job_name), ("partition", spec.partition), ("nodes", spec.nodes),
        ("ntasks", spec.ntasks), ("cpus-per-task", spec.cpus_per_task), ("mem", spec.mem),
        ("gres", gres_value(spec) or ""), ("time", spec.time), ("output", spec.output),
        ("error", spec.error), ("mail-type", spec.mail_type.upper()), ("mail-user", spec.mail_user),
    ]
    return [f"#SBATCH --{name}={value}" for name, value in options if value]


def _staging_prologue(spec: JobSpec) -> list[str]:
    stage_in = " ".join(shlex.quote(f) for f in spec.stage_in)
    stage_out = " ".join(shlex.quote(f) for f in spec.stage_out)
    return [
        "# --- ステージング: $JOBDIR はジョブ終了時に削除されます（資料 p.50–52） ---",
        'if [ -z "${JOBDIR:-}" ] || [ ! -d "$JOBDIR" ]; then',
        '  echo "JOBDIR が利用できません。高速ストレージを使えない環境です" >&2',
        "  exit 1",
        "fi",
        "copy_back() {",
        f"  for f in {stage_out or '__none__'}; do",
        '    [ "$f" = __none__ ] && continue',
        '    if [ -e "$JOBDIR/$f" ]; then',
        '      cp -a "$JOBDIR/$f" "$SLURM_SUBMIT_DIR/" || echo "copy-back に失敗: $f" >&2',
        "    else",
        '      echo "出力が見つかりません: $f" >&2',
        "    fi",
        "  done",
        "}",
        "trap copy_back EXIT",
        f"for f in {stage_in or '__none__'}; do",
        '  [ "$f" = __none__ ] && continue',
        '  cp -a "$SLURM_SUBMIT_DIR/$f" "$JOBDIR/"',
        "done",
        'cd "$JOBDIR"',
        "",
    ]


def render_script(spec: JobSpec) -> str:
    lines = ["#!/bin/bash", *sbatch_directives(spec)]
    lines += [
        f"# hakusan-tui で生成（テンプレート: {TEMPLATES.get(spec.template, TEMPLATES['cpu_single']).label}）",
        "# 未指定の項目はクラスタ既定を使用します",
        "",
        "set -euo pipefail",
        'cd "$SLURM_SUBMIT_DIR"',
        "",
    ]
    if spec.modules:
        lines += [f"module load {shlex.quote(m)}" for m in spec.modules] + [""]
    if spec.use_staging:
        lines += _staging_prologue(spec)
    lines += [spec.command.rstrip("\n"), ""]
    return "\n".join(lines)


def default_script_path(spec: JobSpec, base_dir: str = DEFAULT_JOBS_DIR) -> Path:
    return Path(os.path.expanduser(base_dir)) / spec.job_name / "job.sh"


def sbatch_preview(path: Path, test_only: bool = False) -> str:
    flag = " --test-only" if test_only else ""
    return f"cd {shlex.quote(str(path.parent))} && sbatch --parsable{flag} {shlex.quote(path.name)}"


def save_script(spec: JobSpec, path: Path, overwrite: bool = False) -> Path:
    """スクリプトを保存する。``overwrite=False`` なら既存ファイルがあれば FileExistsError。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if overwrite else os.O_EXCL)
    fd = os.open(path, flags, 0o640)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(render_script(spec))
    return path
