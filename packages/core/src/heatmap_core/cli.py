"""Command line for running stages without Dagster.

Examples::

    heatmap watch add 0xd8da6bf26964af9d7eed9e03e53415d37aa96045 --note vitalik
    heatmap run all
    heatmap --chain ethereum run sync
    heatmap run sync --only-new
    heatmap demo
    heatmap labels import exchanges.csv --source eth-labels
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from heatmap_core import pipeline
from heatmap_core.config import Chain, ChainRegistry, Settings, get_settings
from heatmap_core.db.session import get_engine, session_scope
from heatmap_core.entities.labels import import_labels, read_label_file
from heatmap_core.ingestion.watchlist import add_seed, deactivate
from heatmap_core.logging import configure_logging
from heatmap_core.normalize.pricing import make_price_source
from heatmap_core.primitives import EntityCategory
from heatmap_core.providers.router import ProviderRouter
from heatmap_core.providers.usage_store import SqlUsageStore

STAGES = ("reference", "discovery", "sync", "normalize", "graph", "features", "models")


def _run_stage(stage: str, chain: Chain, settings: Settings, *, only_new: bool = False) -> Any:
    engine = get_engine()
    if stage == "reference":
        return pipeline.seed_reference_data(engine, chain)
    if stage == "discovery":
        store = SqlUsageStore(engine)
        try:
            router = ProviderRouter.from_settings(settings, store=store)
            prices = make_price_source(settings.pricing)
            return pipeline.discover_traders(engine, router, chain, settings, prices).__dict__
        finally:
            store.flush()
    if stage == "sync":
        store = SqlUsageStore(engine)
        try:
            router = ProviderRouter.from_settings(settings, store=store)
            return pipeline.sync_tracked_wallets(
                engine, router, chain, only_new=only_new, tracking=settings.tracking
            ).__dict__
        finally:
            store.flush()
    if stage == "normalize":
        prices = make_price_source(settings.pricing)
        return pipeline.normalize(engine, chain, settings, prices).__dict__
    if stage == "graph":
        return pipeline.refresh_graph(engine, chain, settings)
    if stage == "features":
        return pipeline.compute_behaviour(engine, chain, settings).__dict__
    return pipeline.label_wallets(engine, chain, settings).__dict__


def _print(result: Any) -> None:
    print(json.dumps(result, indent=2, default=str))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="heatmap")
    parser.add_argument("--chain", default="ethereum")
    sub = parser.add_subparsers(dest="command", required=True)

    watch = sub.add_parser("watch", help="manage the watchlist")
    watch_sub = watch.add_subparsers(dest="action", required=True)
    add = watch_sub.add_parser("add")
    add.add_argument("addresses", nargs="+")
    add.add_argument("--note")
    add.add_argument("--priority", type=int, default=100)
    remove = watch_sub.add_parser("remove")
    remove.add_argument("addresses", nargs="+")

    run = sub.add_parser("run", help="run one stage or all of them")
    run.add_argument("stage", choices=[*STAGES, "all"])
    run.add_argument(
        "--only-new", action="store_true", help="sync only wallets that were never synced"
    )

    sub.add_parser("demo", help="load a synthetic dataset and run every stage")

    labels = sub.add_parser("labels", help="manage entity labels")
    labels_sub = labels.add_subparsers(dest="action", required=True)
    imp = labels_sub.add_parser("import", help="import a CSV or JSON list of labelled addresses")
    imp.add_argument("file", type=Path)
    imp.add_argument("--source", required=True, help="name of the list, e.g. eth-labels")
    imp.add_argument(
        "--category",
        choices=[c.value for c in EntityCategory],
        help="category for every row (default: inferred from each row)",
    )

    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    chain = ChainRegistry(settings).get(args.chain)

    commands: dict[str, Callable[[], None]] = {}

    def watch_cmd() -> None:
        with session_scope(get_engine()) as session:
            for address in args.addresses:
                if args.action == "add":
                    entry = add_seed(
                        session, chain.chain_id, address, priority=args.priority, note=args.note
                    )
                    print(f"tracking {entry.address}")
                elif deactivate(session, chain.chain_id, address):
                    print(f"untracked {address}")
                else:
                    print(f"not on watchlist: {address}")

    def run_cmd() -> None:
        stages = STAGES if args.stage == "all" else (args.stage,)
        for stage in stages:
            print(f"== {stage}")
            _print(_run_stage(stage, chain, settings, only_new=args.only_new))

    def demo_cmd() -> None:
        from heatmap_core.demo import run_demo  # noqa: PLC0415  (only needed here)

        _print(run_demo(get_engine(), chain, settings))

    def labels_cmd() -> None:
        rows = read_label_file(args.file)
        category = EntityCategory(args.category) if args.category else None
        with session_scope(get_engine()) as session:
            result = import_labels(
                session, chain.chain_id, rows, source=args.source, category=category
            )
        _print(result.__dict__)

    commands = {"watch": watch_cmd, "run": run_cmd, "demo": demo_cmd, "labels": labels_cmd}
    commands[args.command]()


if __name__ == "__main__":
    main()
