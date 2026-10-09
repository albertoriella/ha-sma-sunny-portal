"""Validate public-release and HACS metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
MANIFEST_PATH = ROOT / "custom_components" / "sma_sunny_portal" / "manifest.json"
HACS_PATH = ROOT / "hacs.json"
RELEASE_VERSION = "0.1.1"
MINIMUM_HOME_ASSISTANT = "2026.9.0"


def _read_json(path: Path) -> dict[str, object]:
    """Read one repository JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_contains_release_metadata() -> None:
    """The custom integration manifest identifies the first public release."""
    manifest = _read_json(MANIFEST_PATH)

    assert manifest["domain"] == "sma_sunny_portal"
    assert manifest["version"] == RELEASE_VERSION
    assert manifest["config_flow"] is True
    assert manifest["codeowners"] == ["@albertoriella"]
    assert manifest["documentation"] == (
        "https://github.com/albertoriella/ha-sma-sunny-portal"
    )
    assert manifest["issue_tracker"] == (
        "https://github.com/albertoriella/ha-sma-sunny-portal/issues"
    )


def test_hacs_manifest_uses_only_supported_keys() -> None:
    """HACS metadata declares the tested minimum Home Assistant release."""
    hacs = _read_json(HACS_PATH)
    supported_keys = {
        "content_in_root",
        "country",
        "filename",
        "hacs",
        "hide_default_branch",
        "homeassistant",
        "name",
        "persistent_directory",
        "zip_release",
    }

    assert set(hacs) <= supported_keys
    assert hacs == {
        "name": "SMA Sunny Portal Forecast",
        "homeassistant": MINIMUM_HOME_ASSISTANT,
    }


def test_changelog_and_documentation_match_release() -> None:
    """User-facing release files describe the actual authentication boundary."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    authentication = (ROOT / "docs" / "manual-authentication.md").read_text(
        encoding="utf-8"
    )

    heading = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.MULTILINE)
    assert heading is not None
    assert heading.group(1) == RELEASE_VERSION
    assert MINIMUM_HOME_ASSISTANT in readme
    assert "one selected plant for each SMA account" in readme
    assert "refresh-token chain" in readme
    assert "/api/v1/measurements/PLANT_ID/consumerbalance/consumption" in (
        authentication
    )
    assert "refresh_token" in authentication

    for path in (
        ROOT / "CONTRIBUTING.md",
        ROOT / "SECURITY.md",
        ROOT / "docs" / "release-checklist.md",
        ROOT / ".github" / "CODEOWNERS",
        ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml",
        ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml",
    ):
        assert path.is_file(), f"missing public-release file: {path.relative_to(ROOT)}"


def test_ci_checks_hacs_and_complete_history_for_secrets() -> None:
    """Release validation covers HACS and the complete Git object history."""
    workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(
        encoding="utf-8"
    )

    assert "uses: hacs/action@main" in workflow
    assert "category: integration" in workflow
    assert "fetch-depth: 0" in workflow
    assert "ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:" in workflow
    assert "--log-opts='--all'" in workflow
