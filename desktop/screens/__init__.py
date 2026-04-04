"""desktop.screens — all application screens.

Simpler screens are fully extracted here.
Complex screens (ClassifyScreen, AIJobScreen, ArticleOverviewScreen) are
imported from GamlaAppen as a bridge during the ongoing migration.
"""
from desktop.screens.name_screen import NameScreen
from desktop.screens.categories_screen import CategoriesScreen
from desktop.screens.source_screen import SourceScreen
from desktop.screens.ai_settings_screen import AISettingsScreen
from desktop.screens.filter_screen import FilterScreen
from desktop.screens.done_screen import DoneScreen

__all__ = [
    "NameScreen",
    "CategoriesScreen",
    "SourceScreen",
    "AISettingsScreen",
    "FilterScreen",
    "DoneScreen",
]
