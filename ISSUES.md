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
