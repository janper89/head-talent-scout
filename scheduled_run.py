"""
Run pipeline only on 1st and 3rd Monday.

Usage:
  python3 scheduled_run.py          # runs ./run.sh only if schedule matches
  python3 scheduled_run.py --force  # always runs
"""

from __future__ import annotations

import argparse
import subprocess
from datetime import date, datetime


def is_first_or_third_monday(d: date) -> bool:
    # Monday == 0
    if d.weekday() != 0:
        return False
    # Week-of-month index: 1..5
    week_index = (d.day - 1) // 7 + 1
    return week_index in (1, 3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--mode", default="full", choices=["full", "test"])
    args = parser.parse_args()

    today = date.today()
    if not args.force and not is_first_or_third_monday(today):
        print(f"⏭️  {today.isoformat()} is not 1st/3rd Monday. Skipping.")
        return

    print(f"▶️  Running pipeline ({args.mode}) on {today.isoformat()}")
    subprocess.check_call(["bash", "./run.sh", args.mode])


if __name__ == "__main__":
    main()

