"""Minimal Home Assistant package surface needed during test collection."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any


def _config_entry_only_schema(domain: str) -> tuple[str, str]:
    """Return a stable marker in place of Home Assistant's real schema."""
    return ("config_entry_only", domain)


homeassistant = ModuleType("homeassistant")
homeassistant.__path__ = []  # type: ignore[attr-defined]
helpers = ModuleType("homeassistant.helpers")
helpers.__path__ = []  # type: ignore[attr-defined]
config_validation = ModuleType("homeassistant.helpers.config_validation")
config_validation.config_entry_only_config_schema = _config_entry_only_schema  # type: ignore[attr-defined]
helpers.config_validation = config_validation  # type: ignore[attr-defined]

COLLECTION_MODULES: dict[str, Any] = {
    "homeassistant": homeassistant,
    "homeassistant.helpers": helpers,
    "homeassistant.helpers.config_validation": config_validation,
}

for module_name, module in COLLECTION_MODULES.items():
    sys.modules.setdefault(module_name, module)
