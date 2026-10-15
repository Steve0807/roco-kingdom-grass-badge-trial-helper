"""One small JSON file of user settings, shared by everything that needs one.

It lives outside the database root (``%APPDATA%/roco-trial-helper/settings.json``
on Windows) so the language, the watched screen region and the last database
survive switching database folders and re-installing the exe.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def settings_path() -> Path:
    base = os.environ.get("APPDATA")
    if not base:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "roco-trial-helper" / "settings.json"


def load() -> dict:
    """Every stored setting, or an empty dict if there is nothing readable."""
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except Exception:                     # missing, unreadable or corrupt file
        return {}
    return data if isinstance(data, dict) else {}


def get(key: str, default=None):
    return load().get(key, default)


def update(**values) -> None:
    """Merge `values` in; a read-only home is not worth crashing over."""
    path = settings_path()
    try:
        data = load()
        data.update(values)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
