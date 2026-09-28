"""Fixtures."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    yield


@pytest.fixture(autouse=True)
def mock_frontend():
    """The test environment has no built frontend; the panel is only registered."""
    with (
        patch("homeassistant.components.frontend.async_setup", AsyncMock(return_value=True)),
        patch(
            "homeassistant.components.panel_custom.async_register_panel", AsyncMock()
        ) as register,
    ):
        yield register


@pytest.fixture(autouse=True)
def fresh_meter_readings(monkeypatch):
    """Readings are shared for under a second between callers; not between tests."""
    from custom_components.rf_devices import meter

    meter._LAST.clear()
    monkeypatch.setattr(meter, "SHARE_FOR", 0)
    yield
