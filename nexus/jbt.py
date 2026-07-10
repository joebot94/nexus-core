"""Read/write .jbt files — the Joebot ecosystem envelope.

Per JBT_Format_Spec v1.1 (docs/reference/JBT_Format_Spec.md): every file is
JSON with a root envelope carrying jbt_type / version / created_at / payload.
Unknown fields are preserved, never errored on.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = ("jbt_type", "version", "created_at", "payload")


class JBTError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise JBTError(f"{path}: not valid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise JBTError(f"{path}: root must be a JSON object")
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise JBTError(f"{path}: missing required .jbt fields: {', '.join(missing)}")
    return data


def new(jbt_type: str, payload: dict[str, Any], *, name: str = "",
        version: str = "1.0", notes: str = "") -> dict[str, Any]:
    doc: dict[str, Any] = {
        "jbt_type": jbt_type,
        "version": version,
        "created_at": _now(),
    }
    if name:
        doc["name"] = name
    if notes:
        doc["notes"] = notes
    doc["payload"] = payload
    return doc


def save(path: str | Path, doc: dict[str, Any]) -> None:
    path = Path(path)
    out = dict(doc)
    if path.exists():
        out["modified_at"] = _now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n")
