import hashlib
import json
from typing import Any


def stable_hash(data: Any) -> str:
    """Calcula hash estable para comparar snapshots."""

    serialized = json.dumps(data, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
