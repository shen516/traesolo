#!/usr/bin/env python3
"""合并 teams 表中的重复球队（同联赛 + 同名）。

用法（在 backend 目录下）:
  python scripts/merge_duplicate_teams.py --dry-run
  python scripts/merge_duplicate_teams.py
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
from services.team_dedup import merge_all_duplicate_teams


def main() -> int:
    parser = argparse.ArgumentParser(description="合并重复球队记录")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅统计重复组与合并计划，不写入数据库",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        stats = merge_all_duplicate_teams(db, dry_run=args.dry_run)
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
