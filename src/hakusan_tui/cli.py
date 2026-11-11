"""起動オプション。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import replace
from pathlib import Path

from hakusan_tui import __version__
from hakusan_tui.adapters.base import ClusterAdapter
from hakusan_tui.adapters.demo import DemoAdapter
from hakusan_tui.adapters.slurm import SlurmAdapter
from hakusan_tui.config import Config, load_config
from hakusan_tui.services.diagnostics import diagnose, format_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hakusan-tui", description="HAKUSAN Slurm TUI")
    parser.add_argument("--demo", action="store_true", help="Slurm不要のサンプル環境で起動")
    parser.add_argument("--readonly", action="store_true", help="閲覧専用（投入・キャンセル無効）")
    parser.add_argument("--profile", default=None, help="サイトプロファイル（既定: hakusan）")
    parser.add_argument("--diagnose", action="store_true", help="軽量な起動前診断を表示して終了")
    parser.add_argument("--config", type=Path, default=None, help="設定ファイルのパス")
    parser.add_argument("--version", action="version", version=f"hakusan-tui {__version__}")
    return parser


def build_config(args: argparse.Namespace) -> Config:
    config = load_config(args.config)
    if args.readonly:
        config = replace(config, safety=replace(config.safety, read_only=True))
    if args.profile:
        config = replace(config, profile=args.profile)
    return replace(config, demo=args.demo)


def build_adapter(config: Config) -> ClusterAdapter:
    return DemoAdapter() if config.demo else SlurmAdapter()


async def _diagnose(adapter: ClusterAdapter) -> str:
    caps = await adapter.detect_capabilities()
    return format_report(diagnose(adapter, caps))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = build_config(args)
    adapter = build_adapter(config)
    if args.diagnose:
        print(asyncio.run(_diagnose(adapter)))
        return 0
    from hakusan_tui.app import HakusanApp  # Textual の import は起動時のみ

    HakusanApp(config=config, adapter=adapter).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
