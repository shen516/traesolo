#!/usr/bin/env python3
"""合并 matches 表中的重复赛事记录。

用法（在 backend 目录下）:
  python scripts/merge_duplicate_matches.py --dry-run
  python scripts/merge_duplicate_matches.py --upcoming-only
  python scripts/merge_duplicate_matches.py --status upcoming
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.database import SessionLocal
from services.crawler_service import CrawlerService
from services.match_dedup import merge_all_duplicate_matches


def main() -> int:
    parser = argparse.ArgumentParser(description="合并重复赛事记录")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅统计重复组，不写入数据库",
    )
    parser.add_argument(
        "--upcoming-only",
        action="store_true",
        help="仅处理未开赛且日期>=今天的赛事",
    )
    parser.add_argument(
        "--status",
        choices=["upcoming", "live", "finished"],
        default=None,
        help="按赛事状态过滤",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        crawler = CrawlerService()
        stats = merge_all_duplicate_matches(
            db,
            crawler._remap_team_id,
            dry_run=args.dry_run,
            status=args.status,
            upcoming_only=args.upcoming_only,
        )
        print(json.dumps(stats, ensure_ascii=False, indent=2, default=str))
        return 0
    except Exception as exc:
        db.rollback()
        print(f"merge failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
