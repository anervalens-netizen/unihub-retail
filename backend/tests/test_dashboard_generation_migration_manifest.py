from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_dashboard_generation_epoch_migration_is_registered_exactly() -> None:
    root = Path(__file__).resolve().parents[1]
    migrations = root / "db" / "migrations"
    filename = "076_v3_dashboard_generation_epoch.sql"
    content = (migrations / filename).read_bytes()
    manifest = json.loads((migrations / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["execution_classes"][filename] == "transactional"
    assert manifest["migrations"][filename] == hashlib.sha256(content).hexdigest()
