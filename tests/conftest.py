"""Explicit test fixtures; production random sources remain untouched."""

import pytest


@pytest.fixture
def wang_debug_cli_runtime(monkeypatch):
    """Reproduce CLI state tests without random debug-root gate rejections.

    Keep one test-only stream across CLI commands and exercise the real
    backend, native sampler and fixed rejection gates. Never reroll a root.
    """
    from ibme import assembly
    from ibme.core.randomness import DeterministicRandom

    original = assembly.build_runtime
    rng = DeterministicRandom(b"target-cli-lifecycle")

    def build_runtime(config, **kwargs):
        assert config.hibe == "mock" and config.ibs == "wang-pw-target"
        assert config.to_dict()["ibs_params"]["n"] == 2
        return original(config, ibs_rng=rng, **kwargs)

    monkeypatch.setattr(assembly, "build_runtime", build_runtime)
