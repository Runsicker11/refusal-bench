import random

import duckdb
import pytest

from warehouse.seed import SEED, build


@pytest.fixture(scope="session")
def con():
    """One seeded in-memory warehouse for the whole test session."""
    c = duckdb.connect(":memory:")
    build(c, random.Random(SEED))
    yield c
    c.close()
