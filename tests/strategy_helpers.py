"""Patch a dependency in strategy_engine and in every scripts/strategies module that imported it by name."""

import importlib
import pkgutil

import strategies
import strategy_engine


def patch_everywhere(monkeypatch, name: str, value) -> None:
    """Replace `name` wherever the strategy code looks it up.

    The strategies live in separate modules that each import what they call, so patching only
    strategy_engine would leave them calling the real thing.
    """
    modules = [strategy_engine] + [importlib.import_module(f"strategies.{m.name}")
                                   for m in pkgutil.iter_modules(strategies.__path__)]
    patched = [m for m in modules if hasattr(m, name)]
    assert patched, f"no strategy module has {name!r}"
    for module in patched:
        monkeypatch.setattr(module, name, value)
