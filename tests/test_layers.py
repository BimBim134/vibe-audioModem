"""Smoke tests for the repository skeleton: the layers exist and stay separate."""

import ast
import importlib
from pathlib import Path

import pytest

LAYER_PACKAGES = ["vibemodem.core", "vibemodem.io", "vibemodem.app", "bench"]

# The core turns bytes into audio samples and back; it must not know about devices,
# files, clocks-as-input, the network or the front ends (ADR 0002).
CORE_FORBIDDEN = {
    "vibemodem.io",
    "vibemodem.app",
    "bench",
    "sounddevice",
    "fastapi",
    "uvicorn",
    "socket",
}


@pytest.mark.parametrize("layer", LAYER_PACKAGES)
def test_layer_is_importable(layer):
    assert importlib.import_module(layer) is not None


def test_core_does_not_depend_on_io_app_or_the_outside_world():
    core_dir = Path(importlib.import_module("vibemodem.core").__file__).parent
    sources = list(core_dir.rglob("*.py"))
    assert sources, "core package has no source files"

    offenders = []
    for source in sources:
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported = [node.module]
            else:
                continue
            for name in imported:
                if any(name == bad or name.startswith(bad + ".") for bad in CORE_FORBIDDEN):
                    offenders.append(f"{source.name}: {name}")

    assert offenders == []
