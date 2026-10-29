"""
auto-pull.py - keeps this folder in sync with GitHub.
Run via auto-pull.bat, or: python auto-pull.py
"""
import os
import subprocess
import sys
import time
from datetime import datetime

INTERVAL = 30

def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)

def ts():
    return datetime.now().strftime("%H:%M:%S")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Verify this is a git repo
    result = run(["git", "rev-parse", "--is-inside-work-tree"])
    if result.returncode != 0:
        print(f"No git repo found in: {script_dir}")
        print("Make sure this file is inside your cloned repo folder.")
        input("Press Enter to exit...")
        sys.exit(1)

    # Get tracking branch
    result = run(["git", "rev-parse", "--abbrev-ref", "@{u}"])
    if result.returncode != 0 or not result.stdout.strip():
        print("Your current branch has no remote tracking branch.")
        print("Run: git checkout -b main origin/main")
        input("Press Enter to exit...")
        sys.exit(1)

    upstream = result.stdout.strip()

    print("=" * 60)
    print(f"  Folder  : {script_dir}")
    print(f"  Tracking: {upstream}")
    print(f"  Interval: every {INTERVAL} seconds")
    print("  Close this window to stop.")
    print("=" * 60)
    print()

    while True:
        try:
            run(["git", "fetch", "--quiet"])

            result = run(["git", "rev-list", "--count", "HEAD..@{u}"])
            behind_str = result.stdout.strip()
            behind = int(behind_str) if behind_str.isdigit() else 0

            if behind == 0:
                print(f"[{ts()}] Up to date.")
            else:
                print(f"[{ts()}] {behind} new commit(s) - pulling...")
                pull = subprocess.run(["git", "pull", "--ff-only"])
                print()

        except Exception as e:
            print(f"[{ts()}] Error: {e}")

        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
