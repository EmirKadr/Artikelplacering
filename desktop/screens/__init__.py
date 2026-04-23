"""desktop.screens — all application screens."""
from desktop.screens.setup_screen import SetupScreen
from desktop.screens.source_screen import SourceScreen
from desktop.screens.ai_settings_screen import AISettingsScreen
from desktop.screens.filter_screen import FilterScreen
from desktop.screens.done_screen import DoneScreen
from desktop.screens.classify_screen import ClassifyScreen
from desktop.screens.ai_job_screen import AIJobScreen

__all__ = [
    "SetupScreen",
    "SourceScreen",
    "AISettingsScreen",
    "FilterScreen",
    "DoneScreen",
    "ClassifyScreen",
    "AIJobScreen",
]
