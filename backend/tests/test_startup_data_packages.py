import importlib

import pytest


class _StubDataPackageService:
    def __init__(self, load_result: bool):
        self._load_result = load_result

    def load(self) -> bool:
        return self._load_result


@pytest.mark.asyncio
async def test_startup_fails_when_data_package_validation_fails(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")

    from core.config import get_settings

    get_settings.cache_clear()

    import main as main_module

    main_module = importlib.reload(main_module)
    stub_service = _StubDataPackageService(load_result=False)

    monkeypatch.setattr(
        main_module.DataPackagesService,
        "from_default_paths",
        lambda: stub_service,
    )

    with pytest.raises(RuntimeError, match="Data package validation failed"):
        async with main_module.app.router.lifespan_context(main_module.app):
            pass


@pytest.mark.asyncio
async def test_startup_sets_data_package_service_on_app_state(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")

    from core.config import get_settings

    get_settings.cache_clear()

    import main as main_module

    main_module = importlib.reload(main_module)
    stub_service = _StubDataPackageService(load_result=True)

    monkeypatch.setattr(
        main_module.DataPackagesService,
        "from_default_paths",
        lambda: stub_service,
    )

    async with main_module.app.router.lifespan_context(main_module.app):
        assert main_module.app.state.data_packages_service is stub_service
