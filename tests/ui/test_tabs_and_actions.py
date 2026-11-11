from dataclasses import replace
from pathlib import Path

import pytest
from textual.widgets import Button, DataTable, Input, TabbedContent

from hakusan_tui.adapters.demo import DemoAdapter
from hakusan_tui.app import TAB_IDS, HakusanApp
from hakusan_tui.config import Config, SafetyConfig
from hakusan_tui.widgets.job_detail import JobDetailScreen
from hakusan_tui.widgets.modals import ConfirmScreen, TextScreen

SIZE = (120, 36)


def make_app(tmp_path: Path, read_only: bool = False) -> HakusanApp:
    config = replace(Config(demo=True), jobs_dir=str(tmp_path / "jobs"),
                     safety=SafetyConfig(read_only=read_only))
    return HakusanApp(config, DemoAdapter())


def active(app: HakusanApp) -> str:
    return app.query_one("#main-tabs", TabbedContent).active


async def test_all_nine_tabs_with_digit_keys(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        for i, tab_id in enumerate(TAB_IDS, start=1):
            await pilot.press(str(i))
            await pilot.pause()
            assert active(app) == tab_id
        assert "デモ" in str(app.query_one("#topbar").render())


async def test_small_terminal_80x24(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(80, 24)) as pilot:
        for i in range(1, 10):
            await pilot.press(str(i))
        await pilot.pause()
        assert active(app) == "help"


async def test_digits_go_into_input_when_focused(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("2", "slash")
        assert isinstance(app.focused, Input)
        await pilot.press("1", "2", "6")
        assert app.focused.value == "126"
        assert active(app) == "my_jobs"
        table = app.query_one("#myjobs-table", DataTable)
        assert table.row_count == 5  # デモの自分のジョブは全て 126xxx
        await pilot.press("escape")


async def test_search_filters_my_jobs(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("2")
        await pilot.pause()
        table = app.query_one("#myjobs-table", DataTable)
        assert table.row_count == 5
        app.query_one("#myjobs-search", Input).value = "train"
        await pilot.pause()
        assert table.row_count == 2


async def test_help_modal_opens_and_closes(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("4", "question_mark")
        await pilot.pause()
        assert isinstance(app.screen, TextScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, TextScreen)


async def test_enter_opens_job_detail_with_demo_log(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("2")
        await pilot.pause()
        app.query_one("#myjobs-table", DataTable).focus()
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert isinstance(app.screen, JobDetailScreen)
        log = str(app.screen.query_one("#job-log").render())
        assert "デモ用のログ" in log and "\x1b" not in log
        await pilot.press("escape")


async def test_cancel_in_demo_asks_then_does_not_execute(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("2")
        await pilot.pause()
        app.query_one("#myjobs-table", DataTable).focus()
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        assert app.focused.id == "no"  # 既定は「やめる」
        await pilot.click("#yes")
        await pilot.pause(0.3)
        messages = [n.message for n in app._notifications]
        assert any("デモモードのため実行しません" in m for m in messages)
        assert app.query_one("#myjobs-table", DataTable).row_count == 5


async def test_cancel_disabled_in_readonly(tmp_path):
    app = make_app(tmp_path, read_only=True)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("2")
        await pilot.pause()
        app.query_one("#myjobs-table", DataTable).focus()
        await pilot.press("c")
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmScreen)
        assert "読取専用" in str(app.query_one("#topbar").render())


async def test_other_users_job_cannot_be_cancelled(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        other = next(j for j in app.ctx.jobs() if j.user != "demo_user")
        app.request_cancel(other)
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmScreen)


async def test_submit_save_then_submit_refused_in_demo(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(140, 50)) as pilot:
        await pilot.press("6")
        await pilot.pause()
        app.query_one("#f-job_name", Input).value = "ui_test"
        await pilot.pause()
        app.query_one("#submit-run", Button).press()  # 保存前の投入は拒否
        await pilot.pause()
        assert any("保存" in n.message for n in app._notifications)
        app.query_one("#save", Button).press()
        await pilot.pause()
        script = tmp_path / "jobs" / "ui_test" / "job.sh"
        assert script.exists() and "#SBATCH --job-name=ui_test" in script.read_text()
        app.query_one("#submit-run", Button).press()
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmScreen)
        assert any("デモモード" in n.message for n in app._notifications)


async def test_use_partition_from_nodes_tab(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=(140, 50)) as pilot:
        await pilot.pause()
        app.use_partition("GPU-1A")
        await pilot.pause()
        assert active(app) == "submit"
        assert "#SBATCH --partition=GPU-1A" in app.query_one("#submit-script").text


async def test_quit_with_unsaved_form_asks(tmp_path):
    app = make_app(tmp_path)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("6")
        app.query_one("#f-job_name", Input).value = "dirty"
        await pilot.pause()
        app.set_focus(None)
        await pilot.press("q")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("escape")


@pytest.mark.parametrize("tab", ["gpu", "nodes", "history", "queue", "dashboard"])
async def test_tabs_render_demo_data(tmp_path, tab):
    app = make_app(tmp_path)
    async with app.run_test(size=SIZE) as pilot:
        app.action_switch_tab(tab)
        await pilot.pause(0.3)
        tables = [t for t in app.query(DataTable) if t.row_count]
        assert tables, f"{tab}: データ行がありません"
