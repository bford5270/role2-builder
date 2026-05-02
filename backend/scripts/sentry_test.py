"""Send a test event to Sentry to verify configuration.

Usage:
  $env:SENTRY_DSN = "<your-dsn>"
  python -m backend.scripts.sentry_test

Sends one info-level message and one captured exception. Both should appear
in your Sentry dashboard within seconds.

The test events are tagged `source=doctor` so you can filter them out of
real production noise later.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        print("SENTRY_DSN env var is unset. Set it first:")
        print('  $env:SENTRY_DSN = "<your-dsn>"')
        return 1

    try:
        import sentry_sdk
    except ImportError:
        print("sentry-sdk is not installed. Run: pip install -r requirements.txt")
        return 1

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "doctor"),
        traces_sample_rate=0.0,
        profiles_sample_rate=0.0,
    )

    # Tag everything from this script so it's easy to filter in the Sentry UI.
    sentry_sdk.set_tag("source", "doctor")

    # 1. Info-level message — verifies the DSN, project, and basic transport.
    sentry_sdk.capture_message(
        "role2-builder Sentry doctor: hello from the test script",
        level="info",
    )
    print("[1/2] sent info message")

    # 2. Captured exception — verifies stacktrace upload + grouping.
    try:
        raise RuntimeError("role2-builder Sentry doctor: deliberate test exception")
    except Exception as e:
        sentry_sdk.capture_exception(e)
    print("[2/2] sent test exception")

    # Force flush so the events ship before the process exits.
    sentry_sdk.flush(timeout=5)
    print()
    print("Both events sent. Check your Sentry dashboard:")
    print("  - one info message titled 'role2-builder Sentry doctor: hello...'")
    print("  - one error titled 'RuntimeError: ...deliberate test exception'")
    print("Both should be tagged source=doctor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
