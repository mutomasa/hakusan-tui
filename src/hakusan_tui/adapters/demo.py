"""デモアダプター。Slurm なしで全タブを体験できる。コマンドは一切実行しない。

データは実際の Slurm 出力形式で書いた ``resources/demo_data`` を、本番と同じパーサーで読む。
値はすべて UI 設計用のダミーであり、HAKUSAN の実際の状態ではない。
"""

from __future__ import annotations

from importlib import resources

from hakusan_tui.adapters import slurm_parsers as p
from hakusan_tui.adapters.hakusan import merge_spart_limits, parse_spart
from hakusan_tui.models import (
    Capabilities,
    CommandResult,
    HistoryRecord,
    Job,
    Node,
    Partition,
    SpartTable,
)

DEMO_USER = "demo_user"
DEMO_NOTICE = "デモモードのため実行しません（コマンドプレビューのみ）"

DEMO_LOG = """\
[demo] これはデモ用のログです。実際のジョブ出力ではありません。
epoch 1/10  loss=2.314  lr=1.0e-04
epoch 2/10  loss=1.982  lr=1.0e-04
epoch 3/10  loss=1.701  lr=9.5e-05
\x1b[32mcheckpoint saved\x1b[0m -> ckpt/epoch3.pt
"""


def _read(name: str) -> str:
    return resources.files("hakusan_tui.resources.demo_data").joinpath(name).read_text("utf-8")


def _refused(argv: list[str]) -> CommandResult:
    return CommandResult(tuple(argv), None, "", DEMO_NOTICE, 0.0, not_found=False)


class DemoAdapter:
    mode = "demo"
    executes_commands = False

    def __init__(self) -> None:
        self.current_user = DEMO_USER
        self.hostname = "hakusan1 (デモ)"

    async def detect_capabilities(self) -> Capabilities:
        return Capabilities(
            slurm_available=True,
            slurm_version="デモ (Slurm未接続)",
            squeue_json=False,
            sacct=True,
            sstat=False,
            spart=True,
            module=True,
            pbs_wrappers=(),
            notes=("デモデータを表示中。実環境の状態ではありません。",),
        )

    async def get_jobs(self) -> list[Job]:
        return p.parse_scontrol_jobs(_read("scontrol_jobs.txt"))

    async def get_nodes(self) -> list[Node]:
        return p.parse_scontrol_nodes(_read("scontrol_nodes.txt"))

    async def get_partitions(self) -> list[Partition]:
        parts = p.parse_scontrol_partitions(_read("scontrol_partitions.txt"))
        return merge_spart_limits(parts, await self.get_spart())

    async def get_job_detail(self, job_id: str) -> Job | None:
        return next((j for j in await self.get_jobs() if j.job_id == job_id), None)

    async def get_history(self, days: int, max_records: int) -> list[HistoryRecord]:
        return p.parse_sacct(_read("sacct.txt"))[:max_records]

    async def get_spart(self) -> SpartTable | None:
        return parse_spart(_read("spart.txt"))

    async def get_start_estimates(self) -> dict[str, object]:
        return {}

    async def get_sstat(self, job_id: str) -> CommandResult:
        return _refused(["sstat", "-j", job_id])

    async def submit_job(self, script_path: str, test_only: bool = False) -> CommandResult:
        return _refused(["sbatch", "--parsable", script_path])

    async def cancel_job(self, job_id: str) -> CommandResult:
        return _refused(["scancel", job_id])

    async def run_readonly_tool(self, name: str, args: tuple[str, ...] = ()) -> CommandResult:
        if name == "module_avail":
            return CommandResult(("module", "-t", "avail"), 0, _read("module_avail.txt"), "", 0.0)
        if name == "module_list":
            return CommandResult(("module", "-t", "list"), 0, "No modules loaded\n", "", 0.0)
        return _refused([name, *args])

    def take_warnings(self) -> list[str]:
        return []

    def read_demo_log(self, path: str) -> str:
        return DEMO_LOG
