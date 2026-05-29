"""Shared entrypoint loader used by both in-process discovery and sandbox worker."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path


def load_factory_from_entrypoint(source_dir: Path, entrypoint: str):
    """Import *entrypoint* (``module:callable``) from *source_dir* and return the callable.

    The function prefers a file-based spec so that extensions with the same
    module name but different source directories don't collide in ``sys.modules``.
    A synthetic, globally-unique module name is derived from the source directory
    name and the dotted module path.
    """
    module_name, _, attr_name = entrypoint.partition(":")
    if not module_name or not attr_name:
        raise ValueError("backend.entrypoint must be 'module:callable'")
    module_rel = module_name.replace(".", "/")
    py_path = source_dir / f"{module_rel}.py"
    package_init = source_dir / module_rel / "__init__.py"
    if py_path.is_file():
        spec = importlib.util.spec_from_file_location(
            f"chironai_ext_{source_dir.name}_{module_name.replace('.', '_')}",
            py_path,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load module from {py_path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    elif package_init.is_file():
        spec = importlib.util.spec_from_file_location(
            f"chironai_ext_{source_dir.name}_{module_name.replace('.', '_')}",
            package_init,
            submodule_search_locations=[str(package_init.parent)],
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load package from {package_init}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    else:
        mod = importlib.import_module(module_name)
    factory = getattr(mod, attr_name, None)
    if factory is None:
        raise AttributeError(f"entrypoint callable not found: {entrypoint}")
    return factory
