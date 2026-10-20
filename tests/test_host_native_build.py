from pathlib import Path
import subprocess

import pytest

from experiments.research import host_native_build as host


def test_compiler_name_is_single_executable(monkeypatch):
    monkeypatch.setenv("CC", "cc --extra-argument")
    with pytest.raises(RuntimeError, match="without arguments"):
        host.compiler("CC", "gcc")


def test_sageloli_rejects_unknown_dependency_mode(tmp_path):
    from experiments.research.candidates.sageloli.ring import native

    with pytest.raises(RuntimeError, match="sage-prefix or host-toolchain"):
        native.build(tmp_path / "native", dependency_mode="implicit")


def test_latte_command_relies_on_host_toolchain_without_machine_paths(tmp_path):
    for name in ("bridge.c", "shake.c", "encrypt.c", "test.c", "randombytes.c", "cpucycles.c"):
        (tmp_path / name).write_text("", encoding="ascii")
    (tmp_path / "compat").mkdir()
    command = host.latte_command(tmp_path, tmp_path / "latte", "a" * 64, "host-cc")
    rendered = " ".join(command)
    assert command[0] == "host-cc"
    assert "bridge.c" in rendered and "shake.c" in rendered and "encrypt.c" in rendered
    assert "test.c" not in rendered and "randombytes.c" not in rendered and "cpucycles.c" not in rendered
    assert "-lgmp" in command and "-lmpfr" in command and "-lmpc" in command
    assert "miniconda" not in rendered and "/nix/store" not in rendered


def test_sageloli_command_relies_on_host_toolchain_without_machine_paths(tmp_path):
    source = Path("native.cpp")
    command = host.sageloli_command(source, tmp_path / "ring.so", "b" * 64, "host-cxx")
    rendered = " ".join(map(str, command))
    assert command[0] == "host-cxx"
    assert "-fopenmp" in command and "-lflint" in command and "-lgmp" in command
    assert "miniconda" not in rendered and "/nix/store" not in rendered


def test_native_isa_compile_removes_only_nix_guard(monkeypatch, tmp_path):
    captured = {}

    def run(command, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setenv("NIX_ENFORCE_NO_NATIVE", "1")
    monkeypatch.setenv("IBME_TEST_MARKER", "kept")
    monkeypatch.setattr(host.subprocess, "run", run)
    host.run_compile(["cc"], tmp_path / "compiler.log", 1, allow_native_isa=True)
    assert "NIX_ENFORCE_NO_NATIVE" not in captured["env"]
    assert captured["env"]["IBME_TEST_MARKER"] == "kept"
