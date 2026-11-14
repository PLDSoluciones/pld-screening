import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pldscreen.cli import demo  # noqa: E402
from pldscreen.config import Settings  # noqa: E402
from pldscreen.service import Service  # noqa: E402


@pytest.fixture()
def svc(tmp_path):
    s = Settings(db_path=str(tmp_path / "t.db"), raw_dir=str(tmp_path / "raw"), inbox_dir=str(tmp_path / "inbox"))
    service = Service(s)
    demo(service)
    return service


@pytest.fixture()
def keys(svc):
    return {"analista": svc.create_user("ana", "analista"), "analista2": svc.create_user("beto", "analista"),
            "supervisor": svc.create_user("sofia", "supervisor"), "supervisor2": svc.create_user("saul", "supervisor"),
            "admin": svc.create_user("root", "admin")}
