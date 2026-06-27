"""
CLI runner for 출마표 (pre-race entry) crawl.

Usage:
    cd backend
    DATABASE_URL=postgresql+asyncpg://... python -m app.ml.crawl.run_entry_crawl
    DATABASE_URL=... python -m app.ml.crawl.run_entry_crawl --date 2026-06-28
    DATABASE_URL=... python -m app.ml.crawl.run_entry_crawl --date 2026-06-28 --tracks SEOUL BUSAN
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ALL_TRACKS = ["SEOUL", "BUSAN", "JEJU"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl KRA 출마표 for a target date")
    parser.add_argument(
        "--date",
        type=datetime.date.fromisoformat,
        default=datetime.date.today() + datetime.timedelta(days=1),
        help="Race date in YYYY-MM-DD format (default: tomorrow)",
    )
    parser.add_argument(
        "--tracks",
        nargs="+",
        choices=ALL_TRACKS,
        default=ALL_TRACKS,
        help="Track names to crawl (default: all)",
    )
    return parser.parse_args()


async def _main() -> None:
    if not os.environ.get("DATABASE_URL"):
        logger.error("DATABASE_URL environment variable not set")
        sys.exit(1)

    args = _parse_args()
    from app.ml.crawl.crawl_entries import crawl_entries

    logger.info("Crawling entries for %s tracks=%s", args.date, args.tracks)
    result = await crawl_entries(target_date=args.date, tracks=args.tracks)

    logger.info(
        "Done — races=%d entries=%d errors=%d",
        result["races_upserted"],
        result["entries_upserted"],
        len(result["errors"]),
    )
    for err in result["errors"]:
        logger.warning("Error: %s", err)

    sys.exit(0 if not result["errors"] else 1)


if __name__ == "__main__":
    asyncio.run(_main())
