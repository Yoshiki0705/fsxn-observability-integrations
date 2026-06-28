"""Root conftest for integrations/ — ensures handler module isolation at runtime.

Each vendor's test_*.py already purges sys.modules["handler"] at import time.
This runtime hook provides an additional safety net: before each test runs,
it verifies that `handler` in sys.modules comes from the correct vendor.
If not, it purges and forces a re-import.
"""

import sys
from pathlib import Path

_HANDLER_MODULES = ["handler", "ems_handler", "fpolicy_handler"]


def pytest_runtest_setup(item):
    """Before each test, verify the handler module matches the test's vendor."""
    fspath = Path(str(item.fspath))
    parts = fspath.parts

    try:
        idx = parts.index("integrations")
        vendor = parts[idx + 1]
    except (ValueError, IndexError):
        return

    lambda_dir = Path(__file__).parent / vendor / "lambda"
    if not lambda_dir.is_dir():
        return

    lambda_dir_str = str(lambda_dir)

    for mod_name in _HANDLER_MODULES:
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        mod_file = getattr(mod, "__file__", "") or ""
        # If the cached module is NOT from this vendor's lambda dir, purge it
        if not mod_file.startswith(lambda_dir_str):
            del sys.modules[mod_name]

    # Ensure this vendor's lambda dir is at the front of sys.path
    if lambda_dir_str not in sys.path:
        sys.path.insert(0, lambda_dir_str)
    elif sys.path[0] != lambda_dir_str:
        sys.path.remove(lambda_dir_str)
        sys.path.insert(0, lambda_dir_str)
