#!/usr/bin/env python3
"""Swing Lab Cron Watchdog — runs Swing Lab commands on schedule.

Bypasses the Hermes gateway cron dispatcher (not persistently running on
this Windows host). Handles scheduling directly via time-based checks.

Schedule (ET, converted to MST/Arizona):
  8:30 AM ET = 5:30 AM MST  — pre-market gap scan
  9:00 AM ET = 6:00 AM MST  — morning macro gate + momentum scan
  2:00 PM ET = 11:00 AM MST — afternoon gate check

Only runs on weekdays (Mon-Fri). Skips weekends.
"""
import subprocess
import sys
import time
from datetime import datetime, date, time as dtime
from pathlib import Path

SWING_LAB_DIR = Path("H:/Other/Claude Projects/Swing Lab")
CHECK_INTERVAL = 60  # seconds between polling

# Schedule: (hour, minute) local MST
SCHEDULES = [
    (5, 30, "premarket", ["uv", "run", "swing-lab", "premarket-gap", "--top", "10"]),
    (6, 0,  "morning",   ["uv", "run", "swing-lab", "gate"]),
    (11, 0, "afternoon", ["uv", "run", "swing-lab", "gate"]),
]

# Track last run per schedule key (avoids re-running same slot)
_last_run: dict[str, date] = {}


def is_weekday() -> bool:
    """Monday=0, Sunday=6"""
    return datetime.now().weekday() < 5


def run_cmd(cmd: list[str], label: str) -> str:
    """Run a command and return its output."""
    try:
        result = subprocess.run(
            cmd,
            cwd=str(SWING_LAB_DIR),
            capture_output=True, text=True, timeout=120,
        )
        output = result.stdout.strip()
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr.strip()}"
        return output
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] {label} exceeded 120s"
    except Exception as e:
        return f"[ERROR] {label}: {e}"


def check_and_run() -> list[str]:
    """Check schedules and run any due commands. Returns list of report lines."""
    if not is_weekday():
        return []

    now = datetime.now()
    today = now.date()
    reports = []

    for hour, minute, label, cmd in SCHEDULES:
        # Check if we're within the 5-minute window for this schedule
        sched = dtime(hour, minute)
        current = dtime(now.hour, now.minute)
        elapsed = (current.hour * 60 + current.minute) - (sched.hour * 60 + sched.minute)

        if 0 <= elapsed < 2 and _last_run.get(label) != today:
            _last_run[label] = today
            print(f"[{now.strftime('%H:%M')}] Running {label}...", flush=True)
            output = run_cmd(cmd, label)
            # Write output to a log file
            log_dir = SWING_LAB_DIR / "results"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"cron_{label}_{today.isoformat()}.log"
            log_file.write_text(
                f"=== {label.upper()} — {now.isoformat()} ===\n\n{output}\n",
                encoding="utf-8",
            )
            reports.append(f"[{now.strftime('%H:%M')}] {label} → {log_file.name}")

    return reports


def main():
    print(f"Swing Lab Cron Watchdog started at {datetime.now().isoformat()}")
    print(f"Schedule (MST/Arizona): premarket=5:30, morning=6:00, afternoon=11:00")
    print(f"Polling every {CHECK_INTERVAL}s. Ctrl+C to stop.")
    print()

    while True:
        try:
            reports = check_and_run()
            for r in reports:
                print(r, flush=True)
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\nWatchdog stopped.")
            break
        except Exception as e:
            print(f"[ERROR] {e}", flush=True)
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
