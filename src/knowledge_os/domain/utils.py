import hashlib
import json
from typing import Any
from uuid import uuid4


def hash_payload(payload: dict[str, Any]) -> str:
    """Deterministic SHA-256 hash of a JSON-serializable payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def new_trace_id() -> str:
    return str(uuid4())
