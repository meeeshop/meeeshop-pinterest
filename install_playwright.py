#!/usr/bin/env python3
"""Utility to install Playwright browsers.

This script is intended to be run in the CI environment before the
Pinterest posting scripts are executed.  It simply calls
``playwright install`` which downloads the required Chromium binaries.
"""

import subprocess
import sys


def main() -> int:
    try:
        subprocess.check_call([sys.executable, "-m", "playwright", "install"], stdout=subprocess.DEVNULL)
    except subprocess.CalledProcessError as exc:
        print(f"Failed to install Playwright browsers: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
