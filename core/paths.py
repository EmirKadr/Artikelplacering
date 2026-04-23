"""Path helpers for source and frozen Windows builds."""
import os
import sys
from pathlib import Path

from core.app_info import APP_NAME


def project_root() -> Path:
    """Return the repository root when running from source."""
    return Path(__file__).resolve().parents[1]


def resource_root() -> Path:
    """Return bundled resource root for PyInstaller, otherwise project root."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return project_root()


def resource_path(*parts: str) -> Path:
    """Resolve a file or directory shipped with the application."""
    return resource_root().joinpath(*parts)


def user_data_dir() -> Path:
    """Return a writable per-user data directory."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / APP_NAME


def user_log_dir() -> Path:
    """Return the writable log directory."""
    if getattr(sys, "frozen", False):
        return user_data_dir() / "logs"
    return project_root() / "data" / "logs"
