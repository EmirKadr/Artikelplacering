# Bygga Windows-app

Det här projektet byggs med PyInstaller till en fristående Windows-appmapp.
Builden körs i en temporär lokal mapp för att undvika OneDrive- och Windows-låsningar.

## Snabbbygge

Kör i CMD från projektroten:

```bat
build_windows.bat
```

Resultat:

- `release\Artikelplacering\Artikelplacering.exe`
- `release\Artikelplacering-0.1.0-win64.zip`
- `release\Artikelplacering-0.1.0-Setup.exe` om Inno Setup 6 finns installerat

Zip-filen kan delas till användare utan Python. Den innehåller appen,
`Installera Artikelplacering.bat`, avinstallation och en kort användar-README.

Om Inno Setup 6 finns installerat skapas även en riktig `Setup.exe`.

## Installer

En Inno Setup-mall finns i:

```text
packaging\windows\Artikelplacering.iss
```

När Inno Setup 6 finns installerat bygger `build_windows.bat` en riktig Setup.exe
från den redan byggda `release\Artikelplacering`-mappen. Det går också att köra:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\windows\build_setup.ps1
```

Installeraren är per-user och kräver inte administratörsrättigheter. Den installeras
i användarens `%LOCALAPPDATA%\Artikelplacering`, skapar genvägar och registrerar
avinstallation.

## Uppdateringar

Appen har `Hjälp -> Sök efter uppdateringar` och gör även en tyst kontroll vid
start. Den läser senaste GitHub Release från `EmirKadr/Artikelplacering`, letar
efter en asset som slutar på `Setup.exe`, laddar ner den och startar installeraren.
Eftersom installeraren är per-user behövs inga admin-rättigheter vid uppdatering.

Versionsnumret finns i `core/app_info.py`. Höj `APP_VERSION`, skapa en tagg som
`v0.2.0` och pusha taggen för att skapa en ny release-build.

Se `RELEASE.md` för hela releaseprocessen. Viktigt: skapa bara en ny release när
Emir uttryckligen ber om det. Vanliga ändringar ska inte automatiskt bli release.

## GitHub artifact

Workflowen `.github/workflows/windows-release.yml` bygger Windows-paketet manuellt
via GitHub Actions (`workflow_dispatch`) eller när en tagg som `v0.1.0` pushas.
Den laddar upp zippen och `Setup.exe` som artifacts. Vid tagg-push laddas samma
filer också upp på GitHub Release så appens updater kan hitta dem.
