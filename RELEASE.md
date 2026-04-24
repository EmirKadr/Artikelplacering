# Releaseprocess

Den här filen beskriver hur vi publicerar en ny version av Artikelplacering så
att installeraren hamnar på GitHub Releases och användare kan uppdatera appen.

## Viktig regel

Skapa inte en ny release för varje ändring.

Vanliga kodändringar ska normalt bara commitas och pushas till `main`. En release
ska bara göras när Emir uttryckligen ber om det, till exempel:

- "gör en release"
- "släpp version 0.2.0"
- "tagga och publicera ny version"
- "nu ska kollegan få en uppdatering"

AI-agenter ska aldrig skapa release-tagg eller publicera GitHub Release utan en
sådan uttrycklig instruktion.

Samma regel finns även i `AGENTS.md` och `CLAUDE.md` så både Codex och Claude
ska följa den.

## Vad som händer vid release

När en tagg som `v0.2.0` pushas startar GitHub Actions-workflowen
`.github/workflows/windows-release.yml`.

Workflowen bygger:

- `Artikelplacering-0.2.0-win64.zip`
- `Artikelplacering-0.2.0-Setup.exe`

Vid tagg-push laddas filerna även upp på GitHub Release. Appens updater läser
senaste GitHub Release och letar efter `Setup.exe`. Om versionen där är högre än
användarens installerade version får användaren frågan att uppdatera.

## Embedded proxy-hemlighet

Den inbäddade Gemini/proxy-nyckeln får aldrig ligga direkt i spårad källkod.

Inför release läser builden i stället dessa GitHub Actions secrets:

- `ARTIKELPLACERING_EMBEDDED_PROXY_API_URL`
- `ARTIKELPLACERING_EMBEDDED_PROXY_TOKEN`
- `ARTIKELPLACERING_EMBEDDED_PROXY_MODEL` (valfri, annars används `gemini-2.5-flash`)

Builden genererar då en lokal, ignorerad fil:

```text
core\embedded_proxy_config.py
```

Den filen ska aldrig committas.

## Steg för ny release

Byt ut `0.2.0` mot versionsnumret som ska släppas.

1. Kontrollera att alla ändringar är klara.

2. Höj versionsnumret i `core/app_info.py`:

   ```py
   APP_VERSION = "0.2.0"
   ```

3. Kör tester:

   ```bat
   set QT_QPA_PLATFORM=offscreen
   pytest -v
   ```

4. Bygg och smoke-testa installeraren lokalt:

   ```bat
   set ARTIKELPLACERING_EMBEDDED_PROXY_API_URL=https://din-proxy.vercel.app/api/gemini/v1
   set ARTIKELPLACERING_EMBEDDED_PROXY_TOKEN=ditt-nya-token
   build_windows.bat
   ```

   Förväntade filer:

   ```text
   release\Artikelplacering-0.2.0-win64.zip
   release\Artikelplacering-0.2.0-Setup.exe
   ```

5. Committa versionshöjningen och eventuella ändringar:

   ```bat
   git status --ignore-submodules=all
   git add .
   git commit -m "Release 0.2.0"
   git push
   ```

6. Skapa och pusha release-taggen:

   ```bat
   git tag v0.2.0
   git push origin v0.2.0
   ```

7. Kontrollera GitHub Actions och GitHub Release:

   - Actions ska bli grön.
   - Releasen `v0.2.0` ska ha `Setup.exe` och zip som assets.

## Vid GitGuardian-varning

Om GitGuardian larmar för ett proxytoken betyder det att hemligheten måste
betraktas som komprometterad.

Gör då detta i ordning:

1. Rotera `PROXY_CLIENT_TOKEN` i Vercel.
2. Lägg in det nya värdet i GitHub Actions secret `ARTIKELPLACERING_EMBEDDED_PROXY_TOKEN`.
3. Se till att källkoden inte längre innehåller token.
4. Skapa en ny release först när Emir uttryckligen ber om det.

## Efter release

Användare får uppdateringen genom:

- automatisk kontroll vid appstart
- eller `Hjälp -> Sök efter uppdateringar`

Installeraren är per-user och kräver inte administratörsrättigheter.
När användaren godkänner uppdateringen laddar appen ner `Setup.exe`, startar den
tyst och stänger appen medan uppdateringen installeras.

## Gör inte detta

- Skapa inte tagg/release för små mellanändringar.
- Pusha inte en tagg utan att först höja `APP_VERSION`.
- Återanvänd inte samma versionsnummer för olika installerare.
- Force-pusha inte release-taggar utan att uttryckligen diskutera det först.
- Ladda inte upp en lokal installer manuellt om den inte matchar exakt version i
  `core/app_info.py`.
