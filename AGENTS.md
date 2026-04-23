# Artikelplacering — Agentguide

Primär guide för AI-agenter (Claude Code, OpenAI Codex m.fl.).

---

## Arkitektur — tre lager

```
core/          ← ren Python, INGA Qt-importer
services/      ← orkestrering, INGA Qt-importer
desktop/       ← all Qt-kod (workers, screens, widgets)
tests/         ← tester per lager
GamlaAppen.py  ← arkiverad original (används under migrering)
```

**Regel:** `core/` och `services/` importerar aldrig `PyQt6`.
Verifiera med: `python -c "import core.<modul>"` — ska fungera utan Qt installerat.

---

## Starta appen

```bat
start.bat                   # Windows (rekommenderat)
python desktop/main.py      # direkt
```

---

## Tester

```bash
pytest tests/ -v                  # alla tester
pytest tests/core/ -v             # bara kärnlogik (kräver ej Qt)
pytest tests/services/ -v         # service-lager
pytest tests/desktop/ -v          # Qt-tester (kräver display eller QT_QPA_PLATFORM=offscreen)
```

CI/headless:
```bash
set QT_QPA_PLATFORM=offscreen
pytest tests/ -v
```

---

## Viktiga filer

| Fil | Syfte |
|-----|-------|
| `core/constants.py` | Alla globala konstanter |
| `core/data_manager.py` | Läser CSV-data, `get_meta()` |
| `core/ai_client.py` | `call_api()` — HTTP mot LLM, retry-logik |
| `core/image_utils.py` | `_encode()`, `_download_image()`, `_safe_name()` |
| `core/knowledge_gen.py` | Genererar kategorikunskap via LLM |
| `core/classifier_core.py` | `_classify_batch()`, `_classify_article()` |
| `services/session_service.py` | Excel import/export (utan Qt-dialog) |
| `desktop/workers/ai_job_worker.py` | QThread-wrapper kring core-logik |
| `desktop/screens/ai_job_screen.py` | Huvud-kanban-vy under AI-jobb |
| `desktop/app.py` | `MainApp` (QMainWindow), navigering |
| `desktop/main.py` | Entry point |

---

## Dataflöde (unidirektionellt — VIKTIGT)

```
CSV-fil (read-only)
  → DataManager (core)
    → AIJobWorker (desktop/workers)
      → knowledge_gen + classifier_core (core)
        → Klassificeringsresultat (dict i minnet)
          → AIJobScreen (GUI redigerar resultat)
            → session_service.export_excel()
```

- GUI redigerar **aldrig** CSV-källdata — bara klassificeringsresultaten.
- `DataManager` är read-only.

---

## Migreringsstatus

| Lager | Status | Moduler |
|-------|--------|---------|
| `core/` | ✅ Klar | constants, data_manager, image_utils, ai_client, knowledge_gen, classifier_core |
| `services/` | ✅ Klar | session_service |
| `desktop/widgets/` | ✅ Klar | HeaderBar, CategoryRow, ArticleListModel, ArticleDelegate, ArticleListView, ImageCard, CategoryColumn, _ItemThumbnailLoader, _ThumbnailLoader |
| `desktop/workers/` | ✅ Klar | AIJobWorker, ImageDownloader, NewCategoryWorker, ReClassifyWorker |
| `desktop/screens/` | ✅ Klar | SetupScreen, SourceScreen, AISettingsScreen, FilterScreen, DoneScreen, ClassifyScreen, AIJobScreen |
| `desktop/app.py` | ✅ Klar | MainApp + navigering + main() |

`desktop/main.py` är nu ett riktigt entry point som importerar från `desktop.app`.
`GamlaAppen.py` är arkiverad (används ej längre).

---

## Klassplacering (snabbreferens)

| Klass | Fil |
|-------|-----|
| `DataManager` | `core/data_manager.py` |
| `call_api` | `core/ai_client.py` |
| `generate_knowledge` | `core/knowledge_gen.py` |
| `classify_batch` | `core/classifier_core.py` |
| `AIJobWorker` | `desktop/workers/ai_job_worker.py` |
| `ImageDownloader` | `desktop/workers/image_downloader.py` |
| `ArticleListModel` | `desktop/widgets/article_list_model.py` |
| `CategoryColumn` | `desktop/widgets/category_column.py` |
| `NewCategoryWorker` | `desktop/workers/new_category_worker.py` |
| `ReClassifyWorker` | `desktop/workers/reclassify_worker.py` |
| `SetupScreen` | `desktop/screens/setup_screen.py` |
| `FilterScreen` | `desktop/screens/filter_screen.py` |
| `DoneScreen` | `desktop/screens/done_screen.py` |
| `ClassifyScreen` | `desktop/screens/classify_screen.py` |
| `AIJobScreen` | `desktop/screens/ai_job_screen.py` |
| `MainApp` | `desktop/app.py` |

---

## Konventioner

- Modulnamn i `core/`: snake_case, beskrivande (`classifier_core.py` inte `classifier.py`)
- Tester: `tests/<lager>/test_<modulnamn>.py`
- Varje modul har sin egen logger: `_logger = logging.getLogger(__name__)`
- Qt-workers delegerar till `core/`-funktioner via dependency injection
- Rena funktioner i `core/` tar `progress_cb` och `stop_flag` som parametrar istället för `self`
- Vid UI-ändringar (signalnamn, knapptext, widget-struktur) ska berörda tester uppdateras i samma commit — tester raderas ej utan ersätts
- Tester hittar widgets via `objectName` eller direktreferens från konstruktorn, aldrig via knapptext eller interna variabler (`_foo`)
- Kör `pytest -m "not ui"` för snabb feedback, `pytest` för fullständig körning
- UI-beteendetester (märkta `@pytest.mark.ui`) körs vid större ändringar och migration
- Kontrollera `ISSUES.md` i början av varje session — om poster finns, meddela användaren antal anmärkningar, risknivå (🔴/🟠/🟡/🟢/⚪) och vad som behöver lagas
- När du lägger till en post i `ISSUES.md`: inkludera alltid Risk, Problem, Orsak, Påverkan, Åtgärd och Filer. Välj risknivå enligt tabellen i ISSUES.md

---

## Release och uppdateringar — VIKTIGT

Full releaseprocess finns i `RELEASE.md`.

AI-agenter (Claude Code, OpenAI Codex m.fl.) får inte skapa release-tagg,
GitHub Release eller publicera ny installerare om inte Emir uttryckligen ber om
det. Vanliga kodändringar ska bara commitas/pushas som vanligt.

Skapa release endast vid tydliga instruktioner som exempelvis:

- "gör en release"
- "släpp version 0.2.0"
- "tagga och publicera ny version"
- "nu ska kollegan få en uppdatering"

När release uttryckligen begärs:

1. Höj `APP_VERSION` i `core/app_info.py`.
2. Kör tester och `build_windows.bat`.
3. Committa och pusha ändringarna.
4. Skapa tagg `vX.Y.Z` och pusha taggen.
5. Kontrollera att GitHub Actions laddar upp `Setup.exe` på GitHub Release.

Force-pusha aldrig release-taggar utan separat uttrycklig instruktion.
