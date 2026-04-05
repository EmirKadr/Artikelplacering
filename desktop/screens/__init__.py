"""desktop.screens — all application screens."""
from desktop.screens.name_screen import NameScreen
from desktop.screens.categories_screen import CategoriesScreen
from desktop.screens.source_screen import SourceScreen
from desktop.screens.ai_settings_screen import AISettingsScreen
from desktop.screens.filter_screen import FilterScreen
from desktop.screens.done_screen import DoneScreen
from desktop.screens.article_overview_screen import ArticleOverviewScreen
from desktop.screens.classify_screen import ClassifyScreen
from desktop.screens.ai_job_screen import AIJobScreen

__all__ = [
    "NameScreen",
    "CategoriesScreen",
    "SourceScreen",
    "AISettingsScreen",
    "FilterScreen",
    "DoneScreen",
    "ArticleOverviewScreen",
    "ClassifyScreen",
    "AIJobScreen",
]
