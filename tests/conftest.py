from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("CITEGEIST_LIVE_TESTS") == "1":
        return

    skip_live = pytest.mark.skip(reason="set CITEGEIST_LIVE_TESTS=1 to run live-source tests")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
