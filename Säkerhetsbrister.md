# Säkerhetsbrister — Bildklassificering

Dokumentet listar identifierade säkerhetsbrister i applikationen, sorterade efter allvarlighetsgrad.
Bristerna är **inte åtgärdade** — dokumentet är i informationssyfte och för framtida prioritering.

Datum: 2026-04-04

---

## KRITISK

### 1. URL-injection via urllib utan protokollvalidering
**Plats:** `ImageDownloader._download()`, `_ThumbnailLoader.run()`

**Beskrivning:**
`urllib.request.urlopen()` anropas med URL:er direkt från CSV-data utan att protokollet valideras.
En skadlig URL som `file:///C:/Windows/System32/drivers/etc/hosts` eller
`http://169.254.169.254/latest/meta-data/` kan användas för att läsa lokala filer
(SSRF — Server-Side Request Forgery) eller nå interna nätverkstjänster.

**Varför farligt:**
En angripare som kan kontrollera artikel-URL:er i CSV-filen kan exfiltrera
känsliga filer från användarens dator eller nå interna system.

**Möjlig åtgärd:**
Validera att URL-protokollet är `http://` eller `https://` innan urlopen anropas.
Blockera RFC1918-adresser (192.168.x.x, 10.x.x.x, 172.16-31.x.x) och loopback (127.x.x.x).

```python
from urllib.parse import urlparse
def _validate_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https")
```

---

### 2. API-nyckel lagras i klartext i minnet
**Plats:** `AIJobWorker.__init__`, `AISettingsScreen`, `MainApp.ai_settings`

**Beskrivning:**
API-nyckeln lagras som en vanlig Python-sträng i applikationens tillstånd utan kryptering.
Den skickas till bakgrundstrådar och finns kvar i minnet under hela sessionens livstid.
En minnesdump eller debugger-session kan avslöja nyckeln.

**Varför farligt:**
API-nycklar ger direkt åtkomst till betalda AI-tjänster. Läckage kan leda till
obehörig användning och ekonomisk skada.

**Möjlig åtgärd:**
Använd `keyring`-biblioteket för säker lagring på OS-nivå. Rensa strängar ur minnet
med `ctypes` efter användning. Använd `QLineEdit.setEchoMode(Password)` för inmatningsfältet.

---

### 3. JSON-deserialisering utan schema-validering
**Plats:** Drag-and-drop MIME-data (`_CARD_MIME`), Excel-sessionsimport

**Beskrivning:**
JSON-data från drag-drop-operationer och Excel-filer deserialiseras med `json.loads()`
utan validering av struktur, typer eller storlek. Extremt nästlad JSON kan orsaka
minneshaveri (JSON bomb). Skadlig data kan sätta applikationen i ett inkonsistent tillstånd.

**Varför farligt:**
En manipulerad Excel-sessionsfil kan lura applikationen att bete sig oväntat,
t.ex. köra AI-klassificering med felaktiga kategorier eller överskriva befintliga resultat.

**Möjlig åtgärd:**
Validera JSON-struktur med `jsonschema`-biblioteket. Begränsa stränglängder och
listor till rimliga maxvärden.

---

### 4. Osäker hantering av temporära filer
**Plats:** `_download_image()`, `ImageDownloader`, tidligare `_import_zip()`

**Beskrivning:**
Temporära filer och kataloger skapas med `tempfile.NamedTemporaryFile()` och
`tempfile.mkdtemp()`. På Windows skapas dessa med standardbehörigheter som kan
tillåta andra användare på samma maskin att läsa filerna. Tempfiler rensas inte
garanterat vid krasch.

**Varför farligt:**
Bilddata och metadata som laddas ner kan innehålla känslig affärsinformation
(artikelbilder, sortiment). Dessa kan läsas av andra användare på delade Windows-system.

**Möjlig åtgärd:**
Sätt explicit åtkomstbehörighet med `os.chmod(path, 0o600)` efter skapande.
Registrera tempfiler för cleanup med `atexit`-modulen för att säkerställa rensning vid krasch.

---

## HÖG

### 5. Otillräcklig URL-validering (SSRF via intern nätverksåtkomst)
**Plats:** `FilterScreen` — URL-kolumnläsning, rad ~4541

**Beskrivning:**
URL:er från CSV-filen kontrolleras bara med `.lower().startswith("http")`.
Det tillåter åtkomst till interna tjänster som `http://localhost:6379` (Redis),
`http://192.168.1.1` (routerkonfig) och AWS metadata-endpoint `http://169.254.169.254`.

**Varför farligt:**
I miljöer med interna nätverkstjänster kan en skadlig CSV-fil orsaka
oavsiktlig åtkomst till känsliga interna resurser.

**Möjlig åtgärd:**
Implementera en domän-vitlista eller blockera privata IP-adressintervall.

---

### 6. HTTP utan HTTPS-tvång för externa API-anrop
**Plats:** `DEFAULT_AI_URL = "http://localhost:1234/v1"`, externa providrar

**Beskrivning:**
Standardvärdet för AI-URL använder HTTP. För externa providrar (Gemini, OpenAI)
används HTTPS, men det finns ingen kontroll som förhindrar att användaren anger
en HTTP-URL mot en extern tjänst.

**Varför farligt:**
En man-in-the-middle-angripare i samma nätverk kan avlyssna API-nycklar och
promptar som skickas i klartext. Bilddata (base64-kodade produktbilder) kan också exponeras.

**Möjlig åtgärd:**
Varna användaren om URL inte börjar med `https://` för icke-localhost adresser.
Verifiera TLS-certifikat (aktiverat som standard i `requests`-biblioteket, men
bör bekräftas explicit).

---

### 7. CSV/Excel-injection i exporterad fil
**Plats:** `_export_excel()`, Excel-export av resultat

**Beskrivning:**
Artikelnummer, beskrivningar och kategorinamn från externa datakällor skrivs
direkt till Excel-celler utan sanering. Om ett värde börjar med `=`, `+`, `-`, `@`
tolkas det som en formel av Excel/LibreOffice Calc.

**Varför farligt:**
En skadlig formel som `=HYPERLINK("http://evil.com","klicka")` eller
`=cmd|'/c calc'!A0` kan köras när mottagaren öppnar filen.
Detta är en känd attackvektor (CSV Injection / Formula Injection).

**Möjlig åtgärd:**
Prefixera celler med ett enkelt citattecken (`'`) om värdet börjar med `=+-@`,
eller använd `openpyxl`'s datavalideringsfunktioner för att markera celler som text.

---

### 8. Avsaknad av filtypsvalidering vid bildöppning
**Plats:** `_encode()`, bildladdning i PIL

**Beskrivning:**
Filer öppnas med `PILImage.open()` enbart baserat på filändelse, utan att
kontrollera filens faktiska innehåll (magic bytes). En fil döpt till `.jpg`
som i verkligheten är en SVG med inbäddad JavaScript eller en skadad binärfil
kan orsaka oväntade fel eller exponera systemet.

**Varför farligt:**
PIL-biblioteket har historiskt haft sårbarheter i sina bildavkodare.
Att öppna opålitliga bilder utan validering ökar attackytan.

**Möjlig åtgärd:**
Använd `python-magic` för att verifiera filens MIME-typ baserat på magic bytes
innan PIL öppnar filen. Avvisa filer som inte är bekräftade bildformat.

---

## MEDEL

### 9. Kategorinamn utan längd- och teckenbegränsning
**Plats:** Kategori-namngivning, `_safe_name()`-funktionen

**Beskrivning:**
Kategorinamn skrivs direkt in i AI-promptar, filnamn och Excel-kolumnrubriker
utan begränsning av längd eller tillåtna tecken. Extremt långa namn kan orsaka
fel i API-anrop eller filsystemet. Unicode-kontrolltecken (t.ex. RTL-override `\u202E`)
kan förvränga hur texten visas.

**Möjlig åtgärd:**
Begränsa kategorinamn till max 50 tecken. Filtrera bort kontrolltecken.
Lägg till validering med regex: `re.match(r'^[\w\-\s]{1,50}$', name)`.

---

### 10. Hårdkodade API-endpoints för externa providrar
**Plats:** `DEFAULT_EXTERNAL_PROVIDERS`-konstanten

**Beskrivning:**
URL:er till externa AI-providrar (Gemini, OpenAI, Anthropic) är hårdkodade
i källkoden. Om en providers endpoint ändras eller komprometteras kan alla
användare av applikationen påverkas utan möjlighet till snabb uppdatering.

**Möjlig åtgärd:**
Läs endpoint-konfiguration från en extern konfigurationsfil som kan uppdateras
oberoende av applikationskoden.

---

### 11. Inga hastighetsbegränsningar på bildnedladdning
**Plats:** `ImageDownloader.run()`

**Beskrivning:**
Bildnedladdning sker sekventiellt utan begränsning av total datastorlek eller
antal försök per domän. `resp.read()` laddar hela bilden i minnet utan storleksgräns.
En skadlig URL kan peka på en oändlig dataström och orsaka minneshaveri.

**Möjlig åtgärd:**
Begränsa nedladdad data per bild (t.ex. max 20 MB). Implementera per-domän
hastighetsbegränsning för att undvika oavsiktlig DDoS mot bildservrar.

---

### 12. Loggfil saknar åtkomstkontroll
**Plats:** `AIJobScreen` — `data/logs/`-katalogen

**Beskrivning:**
Loggfiler skapas i `data/logs/` med standardbehörigheter. På delade Windows-system
kan andra användare läsa loggar som innehåller artikelnummer, kategorier och
eventuellt felmeddelanden med känslig affärsinformation.

**Möjlig åtgärd:**
Sätt explicit åtkomstbehörighet (`os.chmod`) på loggfilen och loggkatalogen
efter skapande för att begränsa läsrättigheter till aktuell användare.

---

## LÅG

### 13. API-URL utan användarkontroll vid sociala ingenjörsattacker
**Plats:** `AISettingsScreen` — API URL-fältet

**Beskrivning:**
En angripare kan via social ingenjörskonst (t.ex. skicka en "konfigurationsfil")
lura en användare att peka AI-URL mot en angriparkontrollerad server.
Applikationen skickar då bilder (bas64-kodade produktbilder) och API-nyckel
till angriparens server utan varning.

**Möjlig åtgärd:**
Visa en tydlig varning när URL ändras från standardvärde. Logga när icke-standardiserade
servrar används.

---

### 14. Avsaknad av integritetsskydd för importerade Excel-sessioner
**Plats:** `_import_excel()`

**Beskrivning:**
Importerade Excel-filer saknar signering eller checksumma. En tredje part som
får tillgång till en sessionsfil kan modifiera kategoridata, klassificeringsresultat
eller AI-kunskapsdata utan att applikationen kan upptäcka manipulationen.

**Möjlig åtgärd:**
Beräkna och verifiera en HMAC-signatur av sessionsdatan vid import.
Alternativt: dokumentera att sessionsfilerna ska behandlas som känsliga och
lagras på säkra platser.
