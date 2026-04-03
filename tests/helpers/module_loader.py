from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_service_module(module_name: str, service_dir: Path, file_name: str = "main.py") -> ModuleType:
    root_dir = service_dir.parents[1]
    file_path = service_dir / file_name

    sys.path.insert(0, str(service_dir))
    sys.path.insert(0, str(root_dir))

    for stale_name in ["main", "auth", "repository", "events", "clients"]:
        sys.modules.pop(stale_name, None)

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
