import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("GRID_DATA_DIR", tempfile.mkdtemp(prefix="grid-test-"))  # never touch the real .data/
os.environ["GRID_STORE"] = "memory"        # tests never touch a real Redis
os.environ["GRID_COLLECTOR"] = "embedded"  # the web app starts its own collector on the in-memory store

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def eng():
    """A private engine (not the app singleton) advanced manually, 2 s per tick."""
    from app.sim.engine import Engine
    return Engine()


def advance(e, seconds: float) -> None:
    for _ in range(int(seconds / 2)):
        e.tick(now=e.now + 2.0)
