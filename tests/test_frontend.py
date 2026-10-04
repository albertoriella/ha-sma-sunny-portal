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


class FakeHass:
    """Minimal Home Assistant frontend surface."""

    def __init__(self) -> None:
        """Initialize mutable integration data and HTTP registry."""
        self.data: dict[str, Any] = {}
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

    def add_extra_js_url(hass: FakeHass, url: str) -> None:
        hass.extra_js_urls.append(url)

    frontend.add_extra_js_url = add_extra_js_url  # type: ignore[attr-defined]
    http.StaticPathConfig = FakeStaticPathConfig  # type: ignore[attr-defined]
    components.frontend = frontend  # type: ignore[attr-defined]
    components.http = http  # type: ignore[attr-defined]

    modules = {
        "homeassistant": homeassistant,
        "homeassistant.components": components,
        "homeassistant.components.frontend": frontend,
        "homeassistant.components.http": http,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    sys.modules.pop(MODULE_NAME, None)
    module = importlib.import_module(MODULE_NAME)
    yield module
    sys.modules.pop(MODULE_NAME, None)


def test_frontend_registration_is_private_local_and_idempotent(
    frontend_module: ModuleType,
) -> None:
    """The card is served locally once, with browser caching disabled."""
    hass = FakeHass()

    asyncio.run(frontend_module.async_register_frontend(hass))
    asyncio.run(frontend_module.async_register_frontend(hass))

    assert len(hass.http.calls) == 1
    static_path = hass.http.calls[0][0]
    assert static_path.url_path == (
        "/sma_sunny_portal/frontend/sma-sunny-portal-energy-card.js"
    )
    assert Path(static_path.path).name == "sma-sunny-portal-energy-card.js"
    assert Path(static_path.path).is_file()
    assert static_path.cache_headers is False
    assert hass.extra_js_urls == [
        "/sma_sunny_portal/frontend/sma-sunny-portal-energy-card.js?v=1"
    ]


def test_frontend_asset_has_no_external_runtime_dependencies() -> None:
    """The shipped card cannot pull executable code from a third party."""
    asset = (
        Path(__file__).parents[1]
        / "custom_components"
        / "sma_sunny_portal"
        / "frontend_assets"
        / "sma-sunny-portal-energy-card.js"
    ).read_text(encoding="utf-8")

    assert "customElements.define(CARD_TAG" in asset
    assert "customElements.define(EDITOR_TAG" in asset
    assert '"sma_sunny_portal/history"' in asset
    assert '"sma_sunny_portal/entries"' in asset
    assert "https://" not in asset
    assert "http://" not in asset
    assert "eval(" not in asset
