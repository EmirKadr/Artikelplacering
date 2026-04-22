# Anmärkningar

Icke-akuta problem som behöver åtgärdas. Hanteras när tid finns.
Uppdateras automatiskt av post-commit hook vid brutna UI-tester.

## Risknivåer

| Nivå | Betydelse |
|------|-----------|
| 🔴 KRITISK | Appkrasch eller dataförlust för användaren — åtgärda omedelbart |
| 🟠 HÖG | Märkbar påverkan på användarupplevelsen — åtgärda snart |
| 🟡 MEDEL | Påverkar testinfrastruktur eller minor UX — åtgärda när tid finns |
| 🟢 LÅG | Kosmetiskt eller marginellt — låg prioritet |
| ⚪ IGNORERA | Ingen praktisk påverkan — behöver inte åtgärdas |

---

## 2026-04-05 — manuellt identifierad
**Risk:** 🟡 MEDEL
**Problem:** `TestArticleOverviewScreen` kraschar med Windows stack overflow (exit code 3221226505)
**Orsak:** Qt thumbnail-loader (_ThumbnailLoader QThread) triggar stack overflow vid testkörning headless
**Påverkan:** Dödar hela pytest-processen om den körs i samma session som övriga tester. Ingen påverkan för användaren — skärmen fungerar normalt i produktion.
**Åtgärd:** Klassen är markerad `@pytest.mark.skip` tills rotorsaken åtgärdas
**Filer:** `tests/desktop/test_screens.py::TestArticleOverviewScreen`, `desktop/screens/article_overview_screen.py`

## 2026-04-22 — flaky Qt-teardown i CategoryColumn
**Risk:** 🟡 MEDEL
**Problem:** Godtyckliga tester i `tests/desktop/test_screens.py` failar med `RuntimeError: wrapped C/C++ object of type ArticleListView has been deleted`. Vilka tester som failar varierar mellan körningar (t.ex. `TestAIJobScreen::test_cleanup_file_handler`, `TestAIJobScreen::test_add_new_column`, `TestClassifyScreenBehavior::test_click_cat_button_index0_emits_correct_name`).
**Orsak:** `CategoryColumn.prepend_item` schemalägger `QTimer.singleShot(30, lambda: self._view.scrollToTop())`. När ett test river widget-hierarkin inom 30 ms fires lambda:n mot en redan raderad `ArticleListView`. Observerat även på `HEAD~1` — inte orsakat av drag-fixen i `cc326e9`.
**Påverkan:** Endast testinfrastruktur — i produktion lever `CategoryColumn` hela sessionen så timern hinner alltid fira mot levande vy. Men post-commit-hooken triggar falska larm.
**Åtgärd:** Använd `QTimer.singleShot(30, self._view.scrollToTop)` med bundet method-ref istället för lambda — method-callen blir no-op om vyn är raderad (Qt hanterar det internt). Alternativt: kontrollera `sip.isdeleted(self._view)` i lambda:n.
**Filer:** `desktop/widgets/category_column.py:120`, `tests/desktop/test_screens.py`
