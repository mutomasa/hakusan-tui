"""ジョブ投入タブ。テンプレート → フォーム → 検証・プレビュー → 保存 → 確認して sbatch。"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Input, Label, Select, Static, TextArea

from hakusan_tui.adapters.slurm_parsers import parse_sbatch_parsable
from hakusan_tui.screens.base import BaseTab
from hakusan_tui.services import submission as sub
from hakusan_tui.widgets.modals import ConfirmScreen

TEXT_FIELDS = (
    ("job_name", "ジョブ名 (-J)", "my_job"),
    ("nodes", "ノード数 (--nodes)", "未指定=クラスタ既定"),
    ("ntasks", "タスク数 (-n, --ntasks)", "プロセス数"),
    ("cpus_per_task", "CPU/タスク (--cpus-per-task)", "スレッド数"),
    ("mem", "メモリ (--mem)", "例 32G"),
    ("gpus", "GPU数 (--gres=gpu:N)", "0 または空=なし"),
    ("gpu_type", "GPUタイプ（任意）", "例 a40 / a100（サイト表記を確認）"),
    ("time", "時間 (--time)", "例 02:00:00"),
    ("output", "標準出力 (-o)", "%x=ジョブ名 %j=ジョブID"),
    ("error", "標準エラー (-e)", "%x-%j.err"),
    ("mail_type", "メール通知 (--mail-type)", "例 END,FAIL"),
    ("mail_user", "メール宛先 (--mail-user)", "you@example.ac.jp"),
    ("modules", "module load（カンマ区切り）", "例 gcc/13.2.0,cuda/12.4"),
    ("stage_in", "ステージング入力（カンマ区切り）", "input.dat"),
    ("stage_out", "ステージング出力（カンマ区切り）", "result.dat"),
)
TUPLE_FIELDS = {"modules", "stage_in", "stage_out"}
LEVEL_STYLE = {"error": "bold red", "warning": "yellow", "info": "cyan"}
LEVEL_LABEL = {"error": "エラー", "warning": "警告", "info": "情報"}


def _split(text: str) -> tuple[str, ...]:
    return tuple(t.strip() for t in text.split(",") if t.strip())


class SubmitTab(BaseTab):
    HELP_TITLE = "ジョブ投入"
    HELP_TEXT = (
        "テンプレートを選び、フォームで資源を指定してジョブスクリプトを作ります（資料 p.40–45）。\n\n"
        "1. 右側に **スクリプト全文** と検証結果が常に表示されます。\n"
        "2. 「保存」で `~/slurm_jobs/<ジョブ名>/job.sh` に保存（既存ファイルは確認なしに上書きしません）。\n"
        "3. 「投入」で `sbatch --parsable` を確認付きで実行します。\n\n"
        "- 未指定の項目はクラスタ既定が使われます（TUIは既定値を推測しません）。\n"
        "- `--ntasks` はプロセス数、`--cpus-per-task` は1プロセスあたりのコア数です。\n"
        "- 検証はTUI内部のチェックで、Slurmに受理されることは保証しません。"
        "`--test-only` にチェックすると Slurm 側の検証だけ行います。"
    )
    COMMANDS = ("sbatch --parsable job.sh", "sbatch --test-only job.sh")

    def __init__(self) -> None:
        super().__init__()
        self._spec = sub.apply_template("cpu_single")
        self._loading = False
        self._saved_path: Path | None = None
        self._saved_spec: sub.JobSpec | None = None
        self._submitted_path: Path | None = None
        self._partition_names: list[str] = []
        self.dirty = False

    # ------------------------------------------------------------ 構築

    def compose(self) -> ComposeResult:
        with Horizontal(classes="split"):
            with VerticalScroll(id="submit-form"):
                yield Label("テンプレート")
                yield Select([(t.label, t.key) for t in sub.TEMPLATES.values()],
                             value="cpu_single", allow_blank=False, id="f-template")
                yield Static(id="template-desc", classes="hint")
                yield Label("パーティション (-p)")
                yield Select([], prompt="クラスタ既定を使用", id="f-partition")
                for name, label, placeholder in TEXT_FIELDS:
                    yield Label(label)
                    yield Input(placeholder=placeholder, id=f"f-{name}")
                yield Checkbox("高速ストレージ（$JOBDIR）ステージングを使う", id="f-use_staging")
                yield Label("実行コマンド（計算ノード上で実行。ログインノードでは実行しません）")
                yield TextArea(id="f-command", language=None, classes="command-editor")
                yield Label("既存スクリプトから投入（パス）")
                yield Input(placeholder="~/work/run.sh", id="existing-path")
                yield Button("既存スクリプトを投入…", id="submit-existing")
            with Vertical(id="submit-preview"):
                yield Label("検証結果", classes="section-title")
                yield Static(id="submit-issues")
                yield Label("生成されるスクリプト", classes="section-title")
                yield TextArea(id="submit-script", read_only=True, language="bash")
                yield Static(id="submit-path", classes="hint")
                with Horizontal(classes="buttons"):
                    yield Checkbox("--test-only", id="f-test-only")
                    yield Button("保存", id="save", variant="primary")
                    yield Button("投入…", id="submit-run", variant="success")

    def on_mount(self) -> None:
        self._load_spec_into_form(self._spec)
        self.update_view()

    def update_view(self) -> None:
        names = [p.name for p in self.ctx.partitions()]
        current = self._spec.partition
        if current and current not in names:
            names.append(current)
        if names != self._partition_names:  # 変化した時だけ差し替え
            self._replace_partition_options(names, current)
        self._refresh_preview()

    def _replace_partition_options(self, names: list[str], current: str) -> None:
        select = self.query_one("#f-partition", Select)
        self._partition_names = names
        with self.prevent(Select.Changed):
            select.set_options([(n, n) for n in names])
            if current:
                select.value = current

    # ------------------------------------------------------------ フォーム⇔spec

    def _load_spec_into_form(self, spec: sub.JobSpec) -> None:
        self._loading = True
        try:
            for name, _label, _ph in TEXT_FIELDS:
                value = getattr(spec, name)
                self.query_one(f"#f-{name}", Input).value = (
                    ",".join(value) if name in TUPLE_FIELDS else value
                )
            self.query_one("#f-use_staging", Checkbox).value = spec.use_staging
            self.query_one("#f-command", TextArea).text = spec.command
            self.query_one("#template-desc", Static).update(sub.TEMPLATES[spec.template].description)
            self._set_partition(spec.partition)
        finally:
            self._loading = False
        self._spec = spec

    def _set_partition(self, name: str) -> None:
        select = self.query_one("#f-partition", Select)
        if not name:
            select.clear()
            return
        if name not in self._partition_names:
            self._replace_partition_options([*self._partition_names, name], name)
        select.value = name

    def _read_form(self) -> sub.JobSpec:
        values: dict[str, object] = {}
        for name, _label, _ph in TEXT_FIELDS:
            text = self.query_one(f"#f-{name}", Input).value.strip()
            values[name] = _split(text) if name in TUPLE_FIELDS else text
        partition = self.query_one("#f-partition", Select).value
        values["partition"] = partition if isinstance(partition, str) else ""
        values["use_staging"] = self.query_one("#f-use_staging", Checkbox).value
        values["command"] = self.query_one("#f-command", TextArea).text
        return replace(self._spec, **values)  # type: ignore[arg-type]

    def _on_form_changed(self) -> None:
        if self._loading:
            return
        self._spec = self._read_form()
        self.dirty = True
        self._refresh_preview()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id and event.input.id.startswith("f-"):
            self._on_form_changed()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "f-command":
            self._on_form_changed()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "f-use_staging":
            self._on_form_changed()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "f-template" and not self._loading:
            self._load_spec_into_form(sub.apply_template(str(event.value), self._read_form()))
            self.dirty = True
            self._refresh_preview()
        elif event.select.id == "f-partition":
            self._on_form_changed()

    # ------------------------------------------------------------ プレビュー

    def issues(self) -> list[sub.Issue]:
        return sub.validate(self._spec, self.ctx.partitions_or_none(), self.ctx.nodes())

    def _refresh_preview(self) -> None:
        issues = self.issues()
        text = Text()
        for issue in issues or [sub.Issue("info", "", "問題は見つかりませんでした（内部検証）")]:
            text.append(f"[{LEVEL_LABEL[issue.level]}] ", style=LEVEL_STYLE[issue.level])
            text.append(f"{issue.field + ': ' if issue.field else ''}{issue.message}\n")
        self.query_one("#submit-issues", Static).update(text)
        self.query_one("#submit-script", TextArea).text = sub.render_script(self._spec)
        path = self._target_path()
        state = "保存済み" if self._is_saved() else "未保存"
        self.query_one("#submit-path", Static).update(
            Text(f"保存先: {path}（{state}）\n投入: {sub.sbatch_preview(path, self._test_only())}")
        )

    def _target_path(self) -> Path:
        return sub.default_script_path(self._spec, self.ctx.config.jobs_dir)

    def _test_only(self) -> bool:
        return self.query_one("#f-test-only", Checkbox).value

    def _is_saved(self) -> bool:
        return self._saved_spec == self._spec and self._saved_path == self._target_path()

    # ------------------------------------------------------------ 外部から

    def set_partition(self, name: str) -> None:
        self._set_partition(name)
        self._on_form_changed()

    def set_template(self, key: str) -> None:
        self.query_one("#f-template", Select).value = key

    def add_modules(self, names: list[str]) -> None:
        field = self.query_one("#f-modules", Input)
        merged = list(dict.fromkeys([*_split(field.value), *names]))
        field.value = ",".join(merged)

    # ------------------------------------------------------------ 保存・投入

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {"save": self._save, "submit-run": self._confirm_submit,
                    "submit-existing": self._confirm_existing}
        handler = handlers.get(event.button.id or "")
        if handler:
            handler()

    def _save(self, overwrite: bool = False) -> bool:
        issues = self.issues()
        if sub.has_errors(issues):
            self.app.notify("エラーを修正してから保存してください", severity="error")
            return False
        path = self._target_path()
        if path.exists() and not overwrite:
            self.app.push_screen(
                ConfirmScreen("上書きの確認", f"既にファイルがあります:\n{path}", f"上書き保存 {path}",
                              "上書きする"),
                lambda ok: self._save(overwrite=True) if ok else None,
            )
            return False
        try:
            sub.save_script(self._spec, path, overwrite=overwrite)
        except OSError as exc:
            self.app.notify(f"保存できません: {exc}", severity="error")
            return False
        self._saved_path, self._saved_spec, self.dirty = path, self._spec, False
        self.app.notify(f"保存しました: {path}")
        self._refresh_preview()
        return True

    def _confirm_submit(self) -> None:
        if not self._is_saved():
            self.app.notify("投入する前に「保存」してください（保存するまで投入しません）",
                            severity="warning")
            return
        assert self._saved_path is not None
        self._ask_submit(self._saved_path, self._submitted_path == self._saved_path)

    def _confirm_existing(self) -> None:
        raw = self.query_one("#existing-path", Input).value.strip()
        path = Path(os.path.expanduser(raw)) if raw else None
        if path is None or not path.is_file():
            self.app.notify("既存のスクリプトファイルが見つかりません", severity="error")
            return
        self._ask_submit(path.resolve(), False)

    def _ask_submit(self, path: Path, resubmit: bool) -> None:
        if not self.ctx.writable:
            self.app.notify("読み取り専用/デモモードのため投入できません（プレビューのみ）",
                            severity="warning")
            return
        body = f"スクリプト: {path}\n"
        if resubmit:
            body += "\n⚠ このスクリプトは既に投入済みです。もう一度投入しますか？\n"
        self.app.push_screen(
            ConfirmScreen("ジョブ投入の確認", body, sub.sbatch_preview(path, self._test_only()),
                          "投入する", danger=False),
            lambda ok: self._submit(path) if ok else None,
        )

    @work(exclusive=True, group="submit")
    async def _submit(self, path: Path) -> None:
        button = self.query_one("#submit-run", Button)
        button.disabled = True  # 二重投入防止
        try:
            result = await self.ctx.adapter.submit_job(str(path), test_only=self._test_only())
        finally:
            button.disabled = False
        if not result.ok:
            self.app.notify(f"sbatch 失敗: {result.error_message()}", severity="error", timeout=15)
            return
        if self._test_only():
            self.app.notify(f"--test-only の結果:\n{(result.stderr or result.stdout).strip()}",
                            timeout=15)
            return
        job_id = parse_sbatch_parsable(result.stdout)
        self._submitted_path = path
        self.app.notify(f"投入しました: Job ID {job_id or '（解析不可: ' + result.stdout.strip() + '）'}"
                        "\n「自分のジョブ」タブ（2）で確認できます", timeout=10)
        self.happ.refresh_jobs(force=True)
