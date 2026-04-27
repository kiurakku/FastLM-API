import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: потребує піднятий docker compose + FASTLM_ADMIN_SECRET",
    )
