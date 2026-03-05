# Bildklassificering

Ett enkelt GUI-verktyg för att manuellt klassificera bilder i kategorier.

## Installation

```bash
pip install -r requirements.txt
```

## Användning

1. Lägg bilder du vill klassificera i mappen `bilder/`
2. Starta programmet:
   ```bash
   python classifier.py
   ```
3. **Skärm 1** – Skriv ett namn på testet (t.ex. `test1`)
4. **Skärm 2** – Lägg till kategorier (t.ex. Hund, Katt, Foder). Klicka `+ Lägg till rad` för fler.
5. **Skärm 3** – Varje bild visas en i taget. Klicka på rätt kategori-knapp (eller **Övrigt**).
   - Bilden kopieras till en mapp som heter `testnamn.Kategori`
   - Klicka **Hoppa över** för att skippa en bild
   - Klicka **Avsluta test** för att avbryta

## Mappstruktur efter klassificering

```
bilder/          ← dina ursprungsbilder
test1.Hund/      ← kopierade bilder klassade som "Hund"
test1.Katt/
test1.Övrigt/
```

## Krav

- Python 3.8+
- Pillow (för att visa jpg/png/webp m.fl.)
- tkinter (ingår i standard Python)
