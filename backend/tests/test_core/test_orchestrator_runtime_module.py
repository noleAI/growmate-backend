from collections import OrderedDict
from types import SimpleNamespace

import pytest

from api.routes import orchestrator_runtime as runtime_route


@pytest.fixture(autouse=True)
def _reset_runtime_state(monkeypatch) -> None:
    monkeypatch.setattr(runtime_route, "_orchestrators_by_session", OrderedDict())
    monkeypatch.setattr(runtime_route, "_shared_state_manager", None)
    monkeypatch.setattr(runtime_route, "_shared_llm", None)
    monkeypatch.setattr(runtime_route, "_shared_data_packages", None)
    monkeypatch.setattr(runtime_route, "_agents_config_cache", None)


def test_get_max_orchestrators_prefers_env_override(monkeypatch) -> None:
    monkeypatch.setenv("ORCHESTRATOR_MAX_SESSIONS", "77")
    monkeypatch.setattr(
        runtime_route,
        "get_settings",
        lambda: SimpleNamespace(orchestrator_max_sessions=12),
    )

    assert runtime_route._get_max_orchestrators() == 77


def test_get_max_orchestrators_falls_back_on_invalid_env(monkeypatch, caplog) -> None:
    monkeypatch.setenv("ORCHESTRATOR_MAX_SESSIONS", "not-a-number")
    monkeypatch.setattr(
        runtime_route,
        "get_settings",
        lambda: SimpleNamespace(orchestrator_max_sessions=25),
    )

    with caplog.at_level("WARNING"):
        result = runtime_route._get_max_orchestrators()

    assert result == 25
    assert "Invalid ORCHESTRATOR_MAX_SESSIONS" in caplog.text


def test_get_max_orchestrators_uses_default_when_setting_missing(monkeypatch) -> None:
    monkeypatch.delenv("ORCHESTRATOR_MAX_SESSIONS", raising=False)
    monkeypatch.setattr(runtime_route, "get_settings", lambda: SimpleNamespace())

    assert (
        runtime_route._get_max_orchestrators()
        == runtime_route._ORCHESTRATOR_MAX_SESSIONS_DEFAULT
    )


def test_cleanup_orchestrator_uses_close_when_shutdown_requires_args() -> None:
    class _Orchestrator:
        def __init__(self) -> None:
            self.closed = False

        def shutdown(self, reason) -> None:
            del reason

        def close(self) -> None:
            self.closed = True

    orchestrator = _Orchestrator()
    runtime_route._cleanup_orchestrator("sess-1", orchestrator)

    assert orchestrator.closed is True


def test_cleanup_orchestrator_schedules_coroutine(monkeypatch) -> None:
    class _Orchestrator:
        async def shutdown(self) -> None:
            return None

    captured: dict[str, object] = {}

    def _create_task_stub(coro):
        captured["coro"] = coro
        coro.close()
        return object()

    monkeypatch.setattr(runtime_route.asyncio, "create_task", _create_task_stub)

    runtime_route._cleanup_orchestrator("sess-2", _Orchestrator())

    assert "coro" in captured


def test_evict_if_needed_removes_oldest(monkeypatch) -> None:
    first = object()
    second = object()
    runtime_route._orchestrators_by_session.update(
        {
            "oldest": first,
            "newest": second,
        }
    )
    cleaned: list[tuple[str, object]] = []

    monkeypatch.setattr(runtime_route, "_get_max_orchestrators", lambda: 2)
    monkeypatch.setattr(
        runtime_route,
        "_cleanup_orchestrator",
        lambda key, orch: cleaned.append((key, orch)),
    )

    runtime_route._evict_if_needed()

    assert list(runtime_route._orchestrators_by_session.keys()) == ["newest"]
    assert cleaned == [("oldest", first)]


def test_remove_orchestrator_cleans_up_existing(monkeypatch) -> None:
    orchestrator = object()
    runtime_route._orchestrators_by_session["sess-9"] = orchestrator
    cleaned: list[tuple[str, object]] = []

    monkeypatch.setattr(
        runtime_route,
        "_cleanup_orchestrator",
        lambda key, orch: cleaned.append((key, orch)),
    )

    runtime_route.remove_orchestrator("sess-9")
    runtime_route.remove_orchestrator("missing")

    assert "sess-9" not in runtime_route._orchestrators_by_session
    assert cleaned == [("sess-9", orchestrator)]


def test_load_agents_config_returns_cached_value(monkeypatch) -> None:
    cached = {"strategy": {"q_learning": {"alpha": 0.1}}}
    monkeypatch.setattr(runtime_route, "_agents_config_cache", cached)

    assert runtime_route._load_agents_config() == cached


def test_load_agents_config_returns_empty_when_file_missing(monkeypatch) -> None:
    class _FakePath:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def resolve(self):
            return self

        @property
        def parents(self):
            return [self, self, self]

        def __truediv__(self, _other):
            return self

        def exists(self) -> bool:
            return False

    monkeypatch.setattr(runtime_route, "Path", _FakePath)

    assert runtime_route._load_agents_config() == {}


def test_build_shared_dependencies_creates_and_reuses_instances(monkeypatch) -> None:
    class _FakeStateManager:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class _FakeLLMService:
        pass

    monkeypatch.setattr(
        runtime_route,
        "get_settings",
        lambda: SimpleNamespace(supabase_url="https://example", supabase_key="secret"),
    )
    monkeypatch.setattr(runtime_route, "StateManager", _FakeStateManager)
    monkeypatch.setattr(runtime_route, "LLMService", _FakeLLMService)

    first_state, first_llm = runtime_route._build_shared_dependencies()
    second_state, second_llm = runtime_route._build_shared_dependencies()

    assert isinstance(first_state, _FakeStateManager)
    assert isinstance(first_llm, _FakeLLMService)
    assert first_state.kwargs["supabase_url"] == "https://example"
    assert first_state.kwargs["supabase_key"] == "secret"
    assert first_state is second_state
    assert first_llm is second_llm


def test_get_shared_data_packages_lazy_loads_service(monkeypatch) -> None:
    class _FakeService:
        def __init__(self) -> None:
            self.loaded = False

        def load(self) -> None:
            self.loaded = True

    service = _FakeService()

    class _FakeDataPackagesService:
        @staticmethod
        def from_default_paths():
            return service

    monkeypatch.setattr(runtime_route, "DataPackagesService", _FakeDataPackagesService)

    loaded = runtime_route._get_shared_data_packages()

    assert loaded is service
    assert service.loaded is True


def test_set_shared_data_packages_overrides_lazy_path() -> None:
    service = object()

    runtime_route.set_shared_data_packages(service)

    assert runtime_route._get_shared_data_packages() is service


def test_build_session_agents_uses_config_values(monkeypatch) -> None:
    class _FakeBayesianTracker:
        def __init__(self, prior=None) -> None:
            self.prior = prior

    class _FakeParticleFilter:
        def __init__(self, config) -> None:
            self.config = config

    class _FakeQLearningAgent:
        def __init__(self, config) -> None:
            self.config = config

    monkeypatch.setattr(
        runtime_route,
        "_load_agents_config",
        lambda: {
            "academic": {"bayesian": {"prior_weights": {"algebra": 0.75}}},
            "empathy": {"particle_filter": {"n_particles": 400}},
            "strategy": {"q_learning": {"alpha": 0.2}},
        },
    )
    monkeypatch.setattr(runtime_route, "BayesianTracker", _FakeBayesianTracker)
    monkeypatch.setattr(runtime_route, "ParticleFilter", _FakeParticleFilter)
    monkeypatch.setattr(runtime_route, "QLearningAgent", _FakeQLearningAgent)

    agents = runtime_route._build_session_agents()

    assert agents["academic"].prior == {"algebra": 0.75}
    assert agents["empathy"].config == {"n_particles": 400}
    assert agents["strategy"].config == {"alpha": 0.2}


def test_build_session_agents_without_prior_uses_default_tracker(monkeypatch) -> None:
    class _FakeBayesianTracker:
        def __init__(self, prior=None) -> None:
            self.prior = prior

    class _FakeParticleFilter:
        def __init__(self, config) -> None:
            self.config = config

    class _FakeQLearningAgent:
        def __init__(self, config) -> None:
            self.config = config

    monkeypatch.setattr(runtime_route, "_load_agents_config", lambda: {})
    monkeypatch.setattr(runtime_route, "BayesianTracker", _FakeBayesianTracker)
    monkeypatch.setattr(runtime_route, "ParticleFilter", _FakeParticleFilter)
    monkeypatch.setattr(runtime_route, "QLearningAgent", _FakeQLearningAgent)

    agents = runtime_route._build_session_agents()

    assert agents["academic"].prior is None
    assert agents["empathy"].config == {}
    assert agents["strategy"].config == {}


def test_get_orchestrator_returns_cached_session_on_move_error(monkeypatch) -> None:
    class _BrokenOrderedDict(OrderedDict):
        def move_to_end(self, key, last=True):
            del key, last
            raise RuntimeError("cannot move")

    cached = object()
    mapping = _BrokenOrderedDict({"sess-x": cached})
    monkeypatch.setattr(runtime_route, "_orchestrators_by_session", mapping)

    result = runtime_route.get_orchestrator("sess-x")

    assert result is cached


def test_get_orchestrator_creates_and_caches_new_instance(monkeypatch) -> None:
    class _FakeOrchestrator:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    called = {"evict": False}

    monkeypatch.setattr(runtime_route, "_evict_if_needed", lambda: called.__setitem__("evict", True))
    monkeypatch.setattr(runtime_route, "_build_shared_dependencies", lambda: ("state", "llm"))
    monkeypatch.setattr(runtime_route, "_build_session_agents", lambda: {"academic": "agent"})
    monkeypatch.setattr(runtime_route, "_get_shared_data_packages", lambda: "data-packages")
    monkeypatch.setattr(runtime_route, "AgenticOrchestrator", _FakeOrchestrator)

    result = runtime_route.get_orchestrator("sess-new")

    assert called["evict"] is True
    assert isinstance(result, _FakeOrchestrator)
    assert result.kwargs["state_mgr"] == "state"
    assert result.kwargs["llm"] == "llm"
    assert result.kwargs["agents"] == {"academic": "agent"}
    assert result.kwargs["data_packages"] == "data-packages"
    assert runtime_route._orchestrators_by_session["sess-new"] is result