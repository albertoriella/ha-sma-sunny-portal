"""Tests for optional Lovelace frontend registration."""

from __future__ import annotations

import asyncio
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

MODULE_NAME = "custom_components.sma_sunny_portal.frontend"
CARD_URL = "/sma_sunny_portal/frontend/sma-sunny-portal-energy-card.js?v=3"
CARD_PATH = "/sma_sunny_portal/frontend/sma-sunny-portal-energy-card.js"


@dataclass(frozen=True)
class FakeStaticPathConfig:
    """Mirror the public StaticPathConfig constructor used by the integration."""

    url_path: str
    path: str
    cache_headers: bool


class FakeHttp:
    """Capture registered static paths."""

    def __init__(self) -> None:
        """Initialize call history."""
        self.calls: list[list[FakeStaticPathConfig]] = []

    async def async_register_static_paths(
        self,
        paths: list[FakeStaticPathConfig],
    ) -> None:
        """Record one registration batch."""
        self.calls.append(paths)


class FakeResourceStorageCollection:
    """Model the lazily loaded public Lovelace resource collection."""

    def __init__(
        self,
        items: list[dict[str, str]] | None = None,
        *,
        fail_loading: bool = False,
    ) -> None:
        """Initialize persistent resources and mutation history."""
        self._items = [dict(item) for item in items or []]
        self.fail_loading = fail_loading
        self.loaded = False
        self.info_calls = 0
        self.created: list[dict[str, str]] = []
        self.updated: list[tuple[str, dict[str, str]]] = []
        self.deleted: list[str] = []

    async def async_get_info(self) -> dict[str, int]:
        """Load storage before exposing its current item count."""
        self.info_calls += 1
        if self.fail_loading:
            raise RuntimeError("synthetic Lovelace storage failure")
        self.loaded = True
        return {"resources": len(self._items)}

    def async_items(self) -> list[dict[str, str]]:
        """Return loaded resources without implicitly loading storage."""
        assert self.loaded
        return [dict(item) for item in self._items]

    async def async_create_item(self, data: dict[str, str]) -> dict[str, str]:
        """Create one normalized storage resource."""
        assert self.loaded
        self.created.append(dict(data))
        item = {
            "id": f"generated-{len(self._items) + 1}",
            "type": data["res_type"],
            "url": data["url"],
        }
        self._items.append(item)
        return dict(item)

    async def async_update_item(
        self,
        item_id: str,
        updates: dict[str, str],
    ) -> dict[str, str]:
        """Update one normalized storage resource."""
        assert self.loaded
        self.updated.append((item_id, dict(updates)))
        for item in self._items:
            if item["id"] != item_id:
                continue
            if "res_type" in updates:
                item["type"] = updates["res_type"]
            if "url" in updates:
                item["url"] = updates["url"]
            return dict(item)
        raise KeyError(item_id)

    async def async_delete_item(self, item_id: str) -> None:
        """Delete one normalized storage resource."""
        assert self.loaded
        self.deleted.append(item_id)
        self._items = [item for item in self._items if item["id"] != item_id]


@dataclass
class FakeLovelaceData:
    """Expose the Lovelace resource mode and collection."""

    resource_mode: str
    resources: object


class FakeHass:
    """Minimal Home Assistant frontend surface."""

    def __init__(
        self,
        *,
        resource_mode: str = "storage",
        resources: object | None = None,
        include_lovelace: bool = True,
    ) -> None:
        """Initialize mutable integration data and HTTP registry."""
        self.data: dict[str, Any] = {}
        if include_lovelace:
            self.data["lovelace"] = FakeLovelaceData(
                resource_mode,
                resources or FakeResourceStorageCollection(),
            )
        self.http = FakeHttp()
        self.extra_js_urls: list[str] = []


@pytest.fixture
def frontend_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import frontend.py against the documented Home Assistant APIs."""
    homeassistant = ModuleType("homeassistant")
    homeassistant.__path__ = []  # type: ignore[attr-defined]
    components = ModuleType("homeassistant.components")
    components.__path__ = []  # type: ignore[attr-defined]
    frontend = ModuleType("homeassistant.components.frontend")
    http = ModuleType("homeassistant.components.http")
    lovelace = ModuleType("homeassistant.components.lovelace")
    lovelace.__path__ = []  # type: ignore[attr-defined]
    resources_module = ModuleType("homeassistant.components.lovelace.resources")

    def add_extra_js_url(hass: FakeHass, url: str, es5: bool = False) -> None:
        del es5
        hass.extra_js_urls.append(url)

    frontend.add_extra_js_url = add_extra_js_url  # type: ignore[attr-defined]
    http.StaticPathConfig = FakeStaticPathConfig  # type: ignore[attr-defined]
    lovelace.LOVELACE_DATA = "lovelace"  # type: ignore[attr-defined]
    lovelace.MODE_STORAGE = "storage"  # type: ignore[attr-defined]
    resources_module.ResourceStorageCollection = (  # type: ignore[attr-defined]
        FakeResourceStorageCollection
    )
    components.frontend = frontend  # type: ignore[attr-defined]
    components.http = http  # type: ignore[attr-defined]
    components.lovelace = lovelace  # type: ignore[attr-defined]
    lovelace.resources = resources_module  # type: ignore[attr-defined]

    modules = {
        "homeassistant": homeassistant,
        "homeassistant.components": components,
        "homeassistant.components.frontend": frontend,
        "homeassistant.components.http": http,
        "homeassistant.components.lovelace": lovelace,
        "homeassistant.components.lovelace.resources": resources_module,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    sys.modules.pop(MODULE_NAME, None)
    module = importlib.import_module(MODULE_NAME)
    yield module
    sys.modules.pop(MODULE_NAME, None)


def test_storage_registration_is_persistent_private_and_idempotent(
    frontend_module: ModuleType,
) -> None:
    """Storage mode creates one persistent module and preserves other resources."""
    existing = {
        "id": "existing-card",
        "type": "module",
        "url": "/hacsfiles/example/example.js",
    }
    resources = FakeResourceStorageCollection([existing])
    hass = FakeHass(resources=resources)

    asyncio.run(frontend_module.async_register_frontend(hass))
    asyncio.run(frontend_module.async_register_frontend(hass))

    assert len(hass.http.calls) == 1
    static_path = hass.http.calls[0][0]
    assert static_path.url_path == CARD_PATH
    assert Path(static_path.path).name == "sma-sunny-portal-energy-card.js"
    assert Path(static_path.path).is_file()
    assert static_path.cache_headers is False

    assert resources.info_calls == 1
    assert resources.created == [{"res_type": "module", "url": CARD_URL}]
    assert resources.updated == []
    assert resources.deleted == []
    assert resources.async_items() == [
        existing,
        {
            "id": "generated-2",
            "type": "module",
            "url": CARD_URL,
        },
    ]
    assert hass.extra_js_urls == []


def test_storage_registration_keeps_current_resource_unchanged(
    frontend_module: ModuleType,
) -> None:
    """A restart does not rewrite an already canonical persistent resource."""
    resources = FakeResourceStorageCollection(
        [{"id": "sma-card", "type": "module", "url": CARD_URL}]
    )
    hass = FakeHass(resources=resources)

    asyncio.run(frontend_module.async_register_frontend(hass))

    assert resources.created == []
    assert resources.updated == []
    assert resources.deleted == []
    assert hass.extra_js_urls == []


def test_storage_registration_updates_stale_resource_and_removes_duplicates(
    frontend_module: ModuleType,
) -> None:
    """Only resources owned by the integration are reconciled."""
    unrelated = {
        "id": "unrelated",
        "type": "module",
        "url": "/local/unrelated.js?v=2",
    }
    resources = FakeResourceStorageCollection(
        [
            unrelated,
            {"id": "sma-old", "type": "js", "url": f"{CARD_PATH}?v=1"},
            {"id": "sma-duplicate", "type": "module", "url": CARD_PATH},
        ]
    )
    hass = FakeHass(resources=resources)

    asyncio.run(frontend_module.async_register_frontend(hass))

    assert resources.created == []
    assert resources.updated == [
        (
            "sma-old",
            {"res_type": "module", "url": CARD_URL},
        )
    ]
    assert resources.deleted == ["sma-duplicate"]
    assert resources.async_items() == [
        unrelated,
        {"id": "sma-old", "type": "module", "url": CARD_URL},
    ]
    assert hass.extra_js_urls == []


@pytest.mark.parametrize(
    ("resource_mode", "include_lovelace"),
    [("yaml", True), ("storage", False)],
)
def test_non_storage_resource_modes_use_frontend_fallback(
    frontend_module: ModuleType,
    resource_mode: str,
    include_lovelace: bool,
) -> None:
    """Read-only or unavailable Lovelace resources retain the safe fallback."""
    resources = FakeResourceStorageCollection()
    hass = FakeHass(
        resource_mode=resource_mode,
        resources=resources,
        include_lovelace=include_lovelace,
    )

    asyncio.run(frontend_module.async_register_frontend(hass))

    assert resources.info_calls == 0
    assert resources.created == []
    assert hass.extra_js_urls == [CARD_URL]


def test_storage_failure_does_not_block_integration_setup(
    frontend_module: ModuleType,
) -> None:
    """An optional resource-store failure falls back to runtime registration."""
    resources = FakeResourceStorageCollection(fail_loading=True)
    hass = FakeHass(resources=resources)

    asyncio.run(frontend_module.async_register_frontend(hass))

    assert len(hass.http.calls) == 1
    assert resources.info_calls == 1
    assert resources.created == []
    assert hass.extra_js_urls == [CARD_URL]


def test_frontend_asset_has_no_external_runtime_dependencies() -> None:
    """The shipped card cannot pull executable code from a third party."""
    asset = (
        Path(__file__).parents[1]
        / "custom_components"
        / "sma_sunny_portal"
        / "frontend_assets"
        / "sma-sunny-portal-energy-card.js"
    ).read_text(encoding="utf-8")

    assert "const registerCustomElementsWhenReady" in asset
    assert "registry?.get(HA_ROOT_TAG)" in asset
    assert "registry.define(CARD_TAG" in asset
    assert "registry.define(EDITOR_TAG" in asset
    assert 'data-series="${key}"' in asset
    assert "this._visibleSeries = new Set(SERIES_KEYS)" in asset
    assert "const zeroY = yFor(0)" in asset
    assert "_renderAccuracy(data, labels, timezone, locale)" in asset
    assert "--sma-solar-color: var(--energy-solar-color, #ff9800)" in asset
    assert (
        "--sma-grid-import-color: var(--energy-grid-consumption-color, #488fc2)"
        in asset
    )
    assert "--sma-grid-export-color: var(--energy-grid-return-color, #8353d1)" in asset
    assert ".actual-pv,\n  .forecast-pv { stroke: var(--sma-solar-color); }" in asset
    assert (
        ".actual-consumption,\n"
        "  .forecast-consumption { stroke: var(--sma-consumption-color); }" in asset
    )
    assert "balanceTop" not in asset
    assert "yBalance" not in asset
    assert '"sma_sunny_portal/history"' in asset
    assert '"sma_sunny_portal/entries"' in asset
    assert "https://" not in asset
    assert "http://" not in asset
    assert "eval(" not in asset
