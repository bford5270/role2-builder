"""ZAP number allocator: unique within a run, and can never spin forever."""
import os

os.environ["EXERCISE_BUCKET"] = ""  # tests must never reach AWS

from backend import main  # noqa: E402


def test_zaps_are_unique_in_a_run():
    main._used_zaps.clear()
    zaps = [main._new_zap() for _ in range(2000)]
    assert len(set(zaps)) == len(zaps)


def test_allocator_resets_instead_of_exhausting(monkeypatch):
    # A set that is already full would make the old loop spin forever.
    monkeypatch.setattr(main, "_used_zaps", {str(n) for n in range(10000, 100000)})
    z = main._new_zap()
    assert z.isdigit() and len(main._used_zaps) == 1
