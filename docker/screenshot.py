"""実Slurmに接続したTUIのスクリーンショットを撮る（開発用）。"""
import asyncio
import sys

from hakusan_tui.adapters.slurm import SlurmAdapter
from hakusan_tui.app import HakusanApp
from hakusan_tui.config import Config


async def main(out_dir: str) -> None:
    app = HakusanApp(Config(), SlurmAdapter())
    async with app.run_test(size=(120, 34)) as pilot:
        await pilot.pause(3)
        for tab in ("dashboard", "queue", "gpu", "history", "submit"):
            app.action_switch_tab(tab)
            await pilot.pause(1.5)
            app.save_screenshot(f"{out_dir}/real_{tab}.svg")


asyncio.run(main(sys.argv[1]))
