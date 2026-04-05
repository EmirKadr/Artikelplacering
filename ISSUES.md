# Anmärkningar

Icke-akuta problem som behöver åtgärdas. Hanteras när tid finns.
Uppdateras automatiskt av post-commit hook vid brutna UI-tester.

## 2026-04-05 — manuellt identifierad
**Problem:** `TestArticleOverviewScreen` kraschar med Windows stack overflow (exit code 3221226505)
**Orsak:** Qt thumbnail-loader (_ThumbnailLoader QThread) triggar stack overflow vid testkörning headless
**Påverkan:** Dödar hela pytest-processen om den körs i samma session som övriga tester
**Åtgärd:** Klassen är markerad `@pytest.mark.skip` tills rotorsaken åtgärdas
**Filer:** `tests/desktop/test_screens.py::TestArticleOverviewScreen`, `desktop/screens/article_overview_screen.py`
