"""Entry point for Artikelplacering desktop app."""
import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _smoke_test() -> int:
    """Minimal packaged-app check used by build_windows.bat."""
    from core.data_manager import DataManager

    DataManager()
    return 0


if "--smoke-test" in sys.argv:
    raise SystemExit(_smoke_test())

from desktop.app import main  # noqa: E402

if __name__ == "__main__":
    main()
