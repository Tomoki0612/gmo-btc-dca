import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "dca.sqlite"
    monkeypatch.setenv("BTC_DCA_DB", str(p))
    from pi.scripts.init_db import init

    init(str(p))
    return str(p)


@pytest.fixture
def conn(db_path):
    from pi.api.db import connect

    c = connect(db_path)
    try:
        yield c
    finally:
        c.close()
