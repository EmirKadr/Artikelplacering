import tkinter as tk
from tkinter import messagebox, filedialog
import csv
import os
import random
import shutil
import tempfile
import threading
import urllib.request
import urllib.error
from pathlib import Path

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

IMAGE_DIR = Path("bilder")
DATA_DIR = Path("data")
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
CATEGORY_COLORS = ["#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#00BCD4", "#E91E63"]

# Zero-like values to hide in info panel
_EMPTY_VALUES = {"", "0", "0,00000", "0.00000", "0,0", "0.0"}


class ImageClassifierApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Bildklassificering")
        self.root.geometry("860x620")
        self.root.configure(bg="#f5f5f5")
        self.root.resizable(True, True)

        self.test_name = ""
        self.categories = []
        self.images = []
        self.current_index = 0
        self.photo = None  # keep reference to avoid GC
        self.retesting_ovrigt = False  # True when re-classifying the Övrigt folder

        # CSV mode
        self.csv_mode = False
        self.csv_data = []    # [{article_number, url, img_path}, …] indexed by self.images
        self.results = []     # [{article_number, url, category}, …] — filled during classify
        self.temp_dir = None  # temp folder for downloaded images
        self._bg_stop = threading.Event()   # set to stop background downloader
        self._ready = set()                 # indices of fully downloaded images
        self._dl_lock = threading.Lock()    # protects _ready

        # Built-in reference data (loaded from data/ folder)
        self.item_data = {}        # article_str → {beskrivning, un_nummer, vikt_brutto, vikt_netto, volym, kategori}
        self.alias_data = {}       # article_str → {ean, enhet, faktor, langd, bredd, hojd}
        self.category_map = {}     # kategori_code → huvudkategori
        self.builtin_attributes = []  # [{article_number, url}] from item_attribute file

        # Custom override paths (None = use built-in)
        self.custom_attribute_path = None
        self.custom_alias_path = None
        self.custom_item_path = None
        self.custom_category_path = None

        self._load_builtin_data()
        self.show_name_screen()

    # ------------------------------------------------------------------ helpers

    def clear(self):
        for k in list("0123456789"):
            self.root.unbind(k)
        for w in self.root.winfo_children():
            w.destroy()

    def make_btn(self, parent, text, command, bg="#4CAF50", fg="white",
                 font_size=11, bold=False, width=None, padx=15, pady=8):
        weight = "bold" if bold else "normal"
        kw = dict(font=("Segoe UI", font_size, weight), bg=bg, fg=fg,
                  relief="flat", cursor="hand2", padx=padx, pady=pady,
                  activebackground=bg, activeforeground=fg)
        if width:
            kw["width"] = width
        btn = tk.Button(parent, text=text, command=command, **kw)
        return btn

    def _cleanup_temp(self):
        self._bg_stop.set()  # stop background downloader
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir = None

    # ------------------------------------------------------------------ data loading

    def _load_builtin_data(self):
        """Scan data/ folder and load built-in reference files."""
        if not DATA_DIR.exists():
            return
        for f in sorted(DATA_DIR.iterdir()):
            name = f.name.lower()
            if not name.endswith(".csv"):
                continue
            if name.startswith("item_attribute"):
                self._load_attribute_file(f)
            elif name.startswith("item_alias"):
                self._load_alias_file(f)
            elif name.startswith("item") and not name.startswith("item_"):
                self._load_item_file(f)
            elif name.startswith("main_category"):
                self._load_main_category_file(f)

    def _read_tsv(self, path):
        """Read a tab/csv file and return (headers, rows) as lists of dicts."""
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                sample = fh.read(4096)
                fh.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
                reader = csv.DictReader(fh, dialect=dialect)
                return list(reader)
        except Exception:
            return []

    def _load_attribute_file(self, path):
        """Load item_attribute file → self.builtin_attributes."""
        rows = self._read_tsv(path)
        self.builtin_attributes = []
        for row in rows:
            art = row.get("Artikel", "").strip()
            namn = row.get("Namn", "").strip()
            varde = row.get("Värde", "").strip()
            if art and namn == "IMG" and varde.lower().startswith("http"):
                self.builtin_attributes.append({"article_number": art, "url": varde})

    def _load_alias_file(self, path):
        """Load item_alias file → self.alias_data."""
        rows = self._read_tsv(path)
        self.alias_data = {}
        for row in rows:
            art = row.get("Artikel", "").strip()
            if not art or art in self.alias_data:
                continue
            self.alias_data[art] = {
                "ean":    row.get("Alias", "").strip(),
                "enhet":  row.get("Enhet", "").strip(),
                "faktor": row.get("Faktor", "").strip(),
                "langd":  row.get("Längd", "").strip(),
                "bredd":  row.get("Bredd", "").strip(),
                "hojd":   row.get("Höjd", "").strip(),
            }

    def _load_item_file(self, path):
        """Load item file → self.item_data."""
        rows = self._read_tsv(path)
        self.item_data = {}
        for row in rows:
            art = row.get("Artikel", "").strip()
            if not art:
                continue
            self.item_data[art] = {
                "beskrivning": row.get("Beskrivning", "").strip(),
                "un_nummer":   row.get("UN nummer", "").strip(),
                "vikt_brutto": row.get("Vikt brutto", "").strip(),
                "vikt_netto":  row.get("Vikt netto", "").strip(),
                "volym":       row.get("Volym", "").strip(),
                "kategori":    row.get("Kategori", "").strip(),
            }

    def _load_main_category_file(self, path):
        """Load main_category file → self.category_map."""
        rows = self._read_tsv(path)
        self.category_map = {}
        for row in rows:
            kat = row.get("Kategori", "").strip()
            hkat = row.get("Huvudkategori", "").strip()
            if kat and hkat:
                self.category_map[kat] = hkat

    def _get_article_meta(self, article_str):
        """Return combined metadata dict for an article, or None if not found."""
        art = article_str.strip()
        result = {}
        if art in self.item_data:
            result.update(self.item_data[art])
        if art in self.alias_data:
            result.update(self.alias_data[art])
        cat_code = result.get("kategori", "")
        if cat_code and cat_code in self.category_map:
            result["huvudkategori"] = self.category_map[cat_code]
        return result if result else None

    def _build_info_panel(self, parent, meta):
        """Build a right-side info panel inside parent (dark bg frame)."""
        panel = tk.Frame(parent, bg="#252525", width=250)
        panel.pack(side=tk.RIGHT, fill=tk.Y)
        panel.pack_propagate(False)

        tk.Label(panel, text="Artikelinfo", font=("Segoe UI", 11, "bold"),
                 bg="#252525", fg="#bbb").pack(pady=(12, 4), padx=12, anchor="w")
        tk.Frame(panel, bg="#444", height=1).pack(fill=tk.X, padx=12, pady=(0, 8))

        fields = [
            ("Beskrivning",   meta.get("beskrivning")),
            ("Huvudkategori", meta.get("huvudkategori")),
            ("Kategori",      meta.get("kategori")),
            ("UN nummer",     meta.get("un_nummer")),
            ("Vikt brutto",   meta.get("vikt_brutto")),
            ("Vikt netto",    meta.get("vikt_netto")),
            ("Volym",         meta.get("volym")),
            ("EAN",           meta.get("ean")),
            ("Enhet",         meta.get("enhet")),
            ("Faktor",        meta.get("faktor")),
            ("Längd",         meta.get("langd")),
            ("Bredd",         meta.get("bredd")),
            ("Höjd",          meta.get("hojd")),
        ]

        for label, value in fields:
            if not value or value in _EMPTY_VALUES:
                continue
            row = tk.Frame(panel, bg="#252525")
            row.pack(fill=tk.X, padx=12, pady=2, anchor="w")
            tk.Label(row, text=f"{label}:", font=("Segoe UI", 9),
                     bg="#252525", fg="#888", anchor="w", width=13).pack(side=tk.LEFT)
            tk.Label(row, text=str(value), font=("Segoe UI", 9),
                     bg="#252525", fg="#eee", anchor="w",
                     wraplength=130, justify="left").pack(side=tk.LEFT)

    # ------------------------------------------------------------------ data files dialog

    def _show_data_files_dialog(self):
        """Dialog for viewing and overriding the 4 built-in data files."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Datafiler")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.configure(bg="#f5f5f5")
        self.root.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() // 2 - 260
        y = self.root.winfo_y() + self.root.winfo_height() // 2 - 200
        dlg.geometry(f"520x420+{x}+{y}")

        tk.Label(dlg, text="Datafiler", font=("Segoe UI", 14, "bold"),
                 bg="#f5f5f5").pack(pady=(16, 4), padx=20, anchor="w")
        tk.Label(dlg, text="Välj egna filer för att ersätta de inbyggda.",
                 font=("Segoe UI", 10), bg="#f5f5f5", fg="#666").pack(padx=20, anchor="w")
        tk.Frame(dlg, bg="#ddd", height=1).pack(fill=tk.X, padx=20, pady=10)

        body = tk.Frame(dlg, bg="#f5f5f5", padx=20)
        body.pack(fill=tk.BOTH, expand=True)

        file_defs = [
            ("Attributes",     "URL + artikelnummer",        "custom_attribute_path",
             self._load_attribute_file),
            ("Alias",          "EAN, enhet, mått",           "custom_alias_path",
             self._load_alias_file),
            ("Item",           "Beskrivning, vikt, volym",   "custom_item_path",
             self._load_item_file),
            ("Huvudkategorier","Kategori-mappning",          "custom_category_path",
             self._load_main_category_file),
        ]

        status_labels = {}

        def make_status(art, attr_name):
            path = getattr(self, attr_name)
            if path:
                return f"Anpassad: {Path(path).name}"
            # check if built-in exists
            counts = {
                "custom_attribute_path": len(self.builtin_attributes),
                "custom_alias_path":     len(self.alias_data),
                "custom_item_path":      len(self.item_data),
                "custom_category_path":  len(self.category_map),
            }
            n = counts.get(attr_name, 0)
            return f"Inbyggd  ({n} poster)" if n else "Ingen fil hittad"

        def pick_file(attr_name, loader, lbl_widget):
            path = filedialog.askopenfilename(
                title="Välj fil",
                filetypes=[("CSV/TSV-filer", "*.csv *.tsv *.txt"), ("Alla filer", "*.*")],
                parent=dlg,
            )
            if not path:
                return
            setattr(self, attr_name, path)
            loader(Path(path))
            lbl_widget.configure(text=f"Anpassad: {Path(path).name}", fg="#1B5E20")

        def reset_file(attr_name, loader, lbl_widget):
            setattr(self, attr_name, None)
            # Reload built-in
            for f in sorted(DATA_DIR.iterdir()) if DATA_DIR.exists() else []:
                n = f.name.lower()
                if attr_name == "custom_attribute_path" and n.startswith("item_attribute") and n.endswith(".csv"):
                    loader(f); break
                elif attr_name == "custom_alias_path" and n.startswith("item_alias") and n.endswith(".csv"):
                    loader(f); break
                elif attr_name == "custom_item_path" and n.startswith("item") and not n.startswith("item_") and n.endswith(".csv"):
                    loader(f); break
                elif attr_name == "custom_category_path" and n.startswith("main_category") and n.endswith(".csv"):
                    loader(f); break
            lbl_widget.configure(text=make_status("", attr_name), fg="#555")
            # Re-evaluate after clear
            lbl_widget.configure(text=make_status(None, attr_name))

        for title, subtitle, attr_name, loader in file_defs:
            row = tk.Frame(body, bg="#f5f5f5", pady=6)
            row.pack(fill=tk.X)

            left = tk.Frame(row, bg="#f5f5f5")
            left.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(left, text=title, font=("Segoe UI", 11, "bold"),
                     bg="#f5f5f5").pack(anchor="w")
            tk.Label(left, text=subtitle, font=("Segoe UI", 9),
                     bg="#f5f5f5", fg="#888").pack(anchor="w")

            path = getattr(self, attr_name)
            status_text = make_status(None, attr_name)
            fg_color = "#1B5E20" if path else "#555"
            lbl = tk.Label(left, text=status_text, font=("Segoe UI", 9, "italic"),
                           bg="#f5f5f5", fg=fg_color)
            lbl.pack(anchor="w")

            btn_frame = tk.Frame(row, bg="#f5f5f5")
            btn_frame.pack(side=tk.RIGHT)
            self.make_btn(btn_frame, "Välj fil", lambda a=attr_name, lo=loader, lb=lbl: pick_file(a, lo, lb),
                          bg="#2196F3", font_size=9, padx=8, pady=4).pack(side=tk.LEFT, padx=(0, 4))
            self.make_btn(btn_frame, "Återställ", lambda a=attr_name, lo=loader, lb=lbl: reset_file(a, lo, lb),
                          bg="#9e9e9e", font_size=9, padx=8, pady=4).pack(side=tk.LEFT)

            tk.Frame(body, bg="#eee", height=1).pack(fill=tk.X, pady=(4, 0))

        self.make_btn(dlg, "Stäng", dlg.destroy,
                      bg="#555", font_size=10).pack(pady=16)

    # ---------------------------------------------------------- screen 1: name

    def show_name_screen(self):
        self._cleanup_temp()
        self.csv_mode = False
        self.csv_data = []
        self.results = []
        self.retesting_ovrigt = False
        self.clear()

        frame = tk.Frame(self.root, bg="#f5f5f5")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(frame, text="Bildklassificering", font=("Segoe UI", 26, "bold"),
                 bg="#f5f5f5", fg="#222").pack(pady=(0, 30))

        tk.Label(frame, text="Namn på testet:", font=("Segoe UI", 13),
                 bg="#f5f5f5", fg="#444").pack(anchor="w")

        self.name_var = tk.StringVar()
        entry = tk.Entry(frame, textvariable=self.name_var, font=("Segoe UI", 13),
                         width=32, relief="solid", bd=1)
        entry.pack(pady=(4, 20), ipady=6)
        entry.focus()

        self.make_btn(frame, "Gå vidare  →", self.validate_name,
                      font_size=12, bold=True).pack()

        entry.bind("<Return>", lambda _: self.validate_name())

    def validate_name(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Fel", "Ange ett namn för testet.")
            return
        safe = "".join(c for c in name if c not in r'\/:*?"<>|').strip()
        if not safe:
            messagebox.showwarning("Fel", "Namnet innehåller ogiltiga tecken.")
            return
        self.test_name = safe
        self.show_categories_screen()

    # ------------------------------------------------- screen 2: categories

    def show_categories_screen(self):
        self.clear()
        self.category_entries = []

        hdr = tk.Frame(self.root, bg="#333", pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"Test: {self.test_name}", font=("Segoe UI", 12, "bold"),
                 bg="#333", fg="white").pack(side=tk.LEFT, padx=20)

        body = tk.Frame(self.root, bg="#f5f5f5", padx=40, pady=20)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(body, text="Kategorier", font=("Segoe UI", 16, "bold"),
                 bg="#f5f5f5").pack(anchor="w", pady=(0, 4))
        tk.Label(body, text="Skriv en kategori per rad. Knappen \"Övrigt\" läggs alltid till automatiskt.",
                 font=("Segoe UI", 10), bg="#f5f5f5", fg="#666").pack(anchor="w", pady=(0, 12))

        self.entries_frame = tk.Frame(body, bg="#f5f5f5")
        self.entries_frame.pack(fill=tk.X)

        for _ in range(3):
            self._add_category_row()

        btn_row = tk.Frame(body, bg="#f5f5f5", pady=16)
        btn_row.pack(fill=tk.X)

        self.make_btn(btn_row, "+ Lägg till rad", self._add_category_row,
                      bg="#2196F3").pack(side=tk.LEFT, padx=(0, 8))
        self.make_btn(btn_row, "Starta klassificering  →", self.validate_categories,
                      bg="#4CAF50", bold=True).pack(side=tk.LEFT)

    def _add_category_row(self):
        row = tk.Frame(self.entries_frame, bg="#f5f5f5")
        row.pack(fill=tk.X, pady=3)

        idx_label = tk.Label(row, font=("Segoe UI", 11), bg="#f5f5f5", fg="#888", width=3)
        idx_label.pack(side=tk.LEFT)

        entry = tk.Entry(row, font=("Segoe UI", 12), width=28, relief="solid", bd=1)
        entry.pack(side=tk.LEFT, padx=(0, 6), ipady=5)

        def remove(r=row, e=entry):
            self.category_entries.remove(e)
            r.destroy()
            self._renumber()

        tk.Button(row, text="✕", font=("Segoe UI", 10), command=remove,
                  bg="#ef5350", fg="white", relief="flat", cursor="hand2",
                  padx=6, pady=4).pack(side=tk.LEFT)

        self.category_entries.append(entry)
        self._renumber()
        entry.focus()

    def _renumber(self):
        for i, e in enumerate(self.category_entries):
            row = e.master
            labels = [w for w in row.winfo_children() if isinstance(w, tk.Label)]
            if labels:
                labels[0].configure(text=f"{i + 1}.")

    def validate_categories(self):
        cats = [e.get().strip() for e in self.category_entries if e.get().strip()]
        if not cats:
            messagebox.showwarning("Fel", "Ange minst en kategori.")
            return
        self.categories = cats
        self.show_source_screen()

    # ----------------------------------------------- screen 2b: source

    def show_source_screen(self):
        self.clear()

        hdr = tk.Frame(self.root, bg="#333", pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"Test: {self.test_name}", font=("Segoe UI", 12, "bold"),
                 bg="#333", fg="white").pack(side=tk.LEFT, padx=20)

        frame = tk.Frame(self.root, bg="#f5f5f5")
        frame.place(relx=0.5, rely=0.55, anchor="center")

        tk.Label(frame, text="Välj bildkälla", font=("Segoe UI", 18, "bold"),
                 bg="#f5f5f5").pack(pady=(0, 8))
        tk.Label(frame, text="Välj om bilderna ska hämtas från lokal mapp eller via artikeldata.",
                 font=("Segoe UI", 10), bg="#f5f5f5", fg="#666").pack(pady=(0, 24))

        self.make_btn(frame, "📁  Från mapp  (bilder/)", self._load_images,
                      bg="#2196F3", font_size=13, bold=True).pack(fill=tk.X, pady=4, ipady=4)

        if self.builtin_attributes:
            n = len(self.builtin_attributes)
            self.make_btn(frame, f"📊  Använd inbyggd data  ({n} artiklar)",
                          self._use_builtin_attributes,
                          bg="#4CAF50", font_size=13, bold=True).pack(fill=tk.X, pady=4, ipady=4)

        self.make_btn(frame, "📄  Ladda upp CSV-fil", self._load_csv,
                      bg="#7B1FA2", font_size=13, bold=True).pack(fill=tk.X, pady=4, ipady=4)

        self.make_btn(frame, "⚙  Byt datafiler…", self._show_data_files_dialog,
                      bg="#546e7a", font_size=10).pack(fill=tk.X, pady=(12, 0), ipady=2)

        self.make_btn(frame, "← Tillbaka", self.show_categories_screen,
                      bg="#9e9e9e", font_size=10).pack(pady=(8, 0))

    # ---------------------------------------------------------- load images (folder)

    def _load_images(self):
        self.csv_mode = False
        if not IMAGE_DIR.exists():
            messagebox.showerror(
                "Mapp saknas",
                f"Mappen \"{IMAGE_DIR}\" hittades inte.\n"
                "Skapa mappen och lägg till bilder, starta sedan om."
            )
            return

        self.images = [f for f in IMAGE_DIR.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS]
        random.shuffle(self.images)

        if not self.images:
            messagebox.showwarning(
                "Inga bilder",
                f"Inga bilder hittades i mappen \"{IMAGE_DIR}\".\n"
                "Stödda format: jpg, jpeg, png, gif, bmp, webp, tiff"
            )
            return

        self.current_index = 0
        self.show_classify_screen()

    # ---------------------------------------------------------- built-in attributes

    def _use_builtin_attributes(self):
        if not self.builtin_attributes:
            messagebox.showerror("Fel", "Inga inbyggda attributdata hittades i data/-mappen.")
            return
        self._download_csv_images(list(self.builtin_attributes))

    # ---------------------------------------------------------- load images (CSV)

    def _load_csv(self):
        path = filedialog.askopenfilename(
            title="Välj CSV-fil",
            filetypes=[("CSV-filer", "*.csv"), ("Alla filer", "*.*")]
        )
        if not path:
            return

        # Parse CSV — col 0 = article number, auto-detect delimiter and URL column
        rows = []
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel  # fallback to comma
                reader = csv.reader(f, dialect)
                all_rows = list(reader)

            # Auto-detect which column contains URLs by scanning first 5 data rows
            url_col = None
            for row in all_rows[:5]:
                for i, cell in enumerate(row):
                    if cell.strip().lower().startswith("http"):
                        url_col = i
                        break
                if url_col is not None:
                    break

            if url_col is None:
                messagebox.showwarning("Ingen URL-kolumn",
                                       "Kunde inte hitta någon kolumn med URL:er (som börjar med 'http').\n"
                                       "Kontrollera att CSV-filen innehåller bild-URL:er.")
                return

            for line_no, row in enumerate(all_rows, 1):
                if len(row) <= url_col:
                    continue
                article = row[0].strip()
                url = row[url_col].strip()
                if not article or not url:
                    continue
                if not url.lower().startswith("http"):
                    continue
                rows.append({"article_number": article, "url": url})

        except Exception as e:
            messagebox.showerror("CSV-fel", f"Kunde inte läsa CSV-filen:\n{e}")
            return

        if not rows:
            messagebox.showwarning("Inga rader", "Inga giltiga rader hittades i CSV-filen.\n"
                                   "Kontrollera att kolumn 1 är artikelnummer och att någon kolumn innehåller URL:er.")
            return

        self._download_csv_images(rows)

    def _download_one(self, i, row):
        """Download a single image. Returns dest path or None on failure."""
        url = row["url"]
        url_path = url.split("?")[0].rstrip("/")
        filename = url_path.split("/")[-1] or f"img_{i + 1}"
        if "." not in Path(filename).suffix:
            filename += ".jpg"
        dest = Path(self.temp_dir) / f"{i:05d}_{filename}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                with open(dest, "wb") as out:
                    out.write(resp.read())
            return dest
        except Exception:
            return None

    def _download_csv_images(self, rows):
        """Download first image immediately, rest in background thread."""
        self.clear()

        # Loading screen for first image only
        hdr = tk.Frame(self.root, bg="#333", pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"Test: {self.test_name}", font=("Segoe UI", 12, "bold"),
                 bg="#333", fg="white").pack(side=tk.LEFT, padx=20)

        frame = tk.Frame(self.root, bg="#f5f5f5")
        frame.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(frame, text="Hämtar första bilden…", font=("Segoe UI", 16, "bold"),
                 bg="#f5f5f5").pack(pady=(0, 16))
        tk.Label(frame, text=f"{len(rows)} bilder totalt — resten hämtas i bakgrunden",
                 font=("Segoe UI", 11), bg="#f5f5f5", fg="#555").pack()
        self.root.update()

        self.temp_dir = tempfile.mkdtemp(prefix="bildklassificering_")
        self._bg_stop.clear()
        self._ready = set()

        random.shuffle(rows)

        # Pre-populate csv_data and images list (img_path filled as downloads complete)
        self.csv_mode = True
        self.csv_data = [{"article_number": r["article_number"], "url": r["url"], "img_path": None}
                         for r in rows]
        self.images = [None] * len(rows)
        self.results = []
        self.current_index = 0

        # Download first image synchronously
        dest = self._download_one(0, rows[0])
        if dest is None:
            messagebox.showerror("Fel", "Kunde inte ladda ner första bilden.\n"
                                 "Kontrollera att URL:erna är korrekta.")
            self.show_source_screen()
            return
        self.csv_data[0]["img_path"] = dest
        self.images[0] = dest
        with self._dl_lock:
            self._ready.add(0)

        # Start background thread for the rest
        def bg_worker():
            for i, row in enumerate(rows[1:], start=1):
                if self._bg_stop.is_set():
                    break
                d = self._download_one(i, row)
                if d:
                    self.csv_data[i]["img_path"] = d
                    self.images[i] = d
                with self._dl_lock:
                    self._ready.add(i)

        t = threading.Thread(target=bg_worker, daemon=True)
        t.start()

        self.show_classify_screen()

    # ----------------------------------------------- screen 3: classify

    def show_classify_screen(self):
        self.clear()

        if self.current_index >= len(self.images):
            self.show_done_screen()
            return

        # If background download hasn't finished this image yet, show waiting screen
        if self.csv_mode and self.current_index not in self._ready:
            self._show_waiting_screen()
            return

        img_path = self.images[self.current_index]

        # ── Header bar
        hdr = tk.Frame(self.root, bg="#333", pady=8)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"Test: {self.test_name}", font=("Segoe UI", 11, "bold"),
                 bg="#333", fg="white").pack(side=tk.LEFT, padx=16)
        tk.Label(hdr,
                 text=f"Bild {self.current_index + 1} av {len(self.images)}",
                 font=("Segoe UI", 11), bg="#333", fg="#bbb").pack(side=tk.RIGHT, padx=16)

        # ── Content area: image (left) + optional info panel (right)
        content_area = tk.Frame(self.root, bg="#1a1a1a")
        content_area.pack(fill=tk.BOTH, expand=True)

        # Info panel (right) — only in CSV mode when metadata exists
        if self.csv_mode:
            article_str = str(self.csv_data[self.current_index]["article_number"])
            meta = self._get_article_meta(article_str)
            if meta:
                self._build_info_panel(content_area, meta)

        # Image area (takes remaining space)
        img_area = tk.Frame(content_area, bg="#1a1a1a")
        img_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.img_label = tk.Label(img_area, bg="#1a1a1a")
        self.img_label.pack(expand=True, pady=8)
        self._display_image(img_path)

        # ── Filename / article number
        if self.csv_mode:
            meta_row = self.csv_data[self.current_index]
            info_text = f"Artikel: {meta_row['article_number']}   |   {img_path.name}"
        else:
            info_text = img_path.name
        tk.Label(self.root, text=info_text, font=("Segoe UI", 9),
                 bg="#f5f5f5", fg="#999").pack(pady=(4, 0))

        # ── Category buttons (numpad layout)
        cat_frame = tk.Frame(self.root, bg="#f5f5f5", pady=6)
        cat_frame.pack(fill=tk.X, padx=16)

        inner = tk.Frame(cat_frame, bg="#f5f5f5")
        inner.pack()

        # key 1-9 → categories, key 0 → Övrigt
        key_map = {}  # key_num → (label, color, category_name)
        for i, cat in enumerate(self.categories[:9]):
            key_num = i + 1
            color = CATEGORY_COLORS[i % len(CATEGORY_COLORS)]
            key_map[key_num] = (cat, color)
        key_map[0] = ("Övrigt", "#757575")

        # Numpad rows: 7 8 9 / 4 5 6 / 1 2 3 / 0
        for row_keys in [[7, 8, 9], [4, 5, 6], [1, 2, 3], [0]]:
            row_frame = tk.Frame(inner, bg="#f5f5f5")
            row_frame.pack(pady=2)
            for k in row_keys:
                if k in key_map:
                    cat_name, color = key_map[k]
                    label = f"{cat_name} ({k})"
                    self.make_btn(row_frame, label, lambda c=cat_name: self._classify(c),
                                  bg=color, bold=True, width=14).pack(side=tk.LEFT, padx=3)
                else:
                    # Empty placeholder to keep alignment
                    tk.Frame(row_frame, width=112, height=1, bg="#f5f5f5").pack(side=tk.LEFT, padx=3)

        # Keyboard shortcuts
        for k, (cat_name, _) in key_map.items():
            self.root.bind(str(k), lambda e, c=cat_name: self._classify(c))

        # ── Control row
        ctrl = tk.Frame(self.root, bg="#f5f5f5", pady=4)
        ctrl.pack(fill=tk.X, padx=16)

        self.make_btn(ctrl, "Hoppa över", self._skip,
                      bg="#e0e0e0", fg="#333", font_size=10).pack(side=tk.LEFT)
        self.make_btn(ctrl, "+ Ny kategori", self._add_category_during_test,
                      bg="#FF9800", font_size=10).pack(side=tk.LEFT, padx=(8, 0))
        self.make_btn(ctrl, "Avsluta test", self._confirm_end,
                      bg="#e53935", font_size=10).pack(side=tk.RIGHT)

    def _show_waiting_screen(self):
        """Show a 'waiting for download' screen and retry when image is ready."""
        self.clear()
        hdr = tk.Frame(self.root, bg="#333", pady=8)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"Test: {self.test_name}", font=("Segoe UI", 11, "bold"),
                 bg="#333", fg="white").pack(side=tk.LEFT, padx=16)
        tk.Label(hdr, text=f"Bild {self.current_index + 1} av {len(self.images)}",
                 font=("Segoe UI", 11), bg="#333", fg="#bbb").pack(side=tk.RIGHT, padx=16)

        frame = tk.Frame(self.root, bg="#f5f5f5")
        frame.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(frame, text="Väntar på nedladdning…", font=("Segoe UI", 14, "bold"),
                 bg="#f5f5f5", fg="#555").pack(pady=(0, 8))

        with self._dl_lock:
            done = len(self._ready)
        tk.Label(frame, text=f"{done} av {len(self.images)} bilder klara",
                 font=("Segoe UI", 11), bg="#f5f5f5", fg="#888").pack()

        def poll():
            if self.current_index in self._ready:
                self.show_classify_screen()
            else:
                self.root.after(300, poll)

        self.root.after(300, poll)

    def _display_image(self, path):
        try:
            if PIL_AVAILABLE:
                img = Image.open(path)
                img.thumbnail((780, 380), Image.LANCZOS)
                self.photo = ImageTk.PhotoImage(img)
            else:
                self.photo = tk.PhotoImage(file=str(path))
            self.img_label.configure(image=self.photo, text="")
        except Exception as e:
            self.img_label.configure(image="", text=f"Kunde inte visa bild:\n{e}",
                                     fg="white", font=("Segoe UI", 11))

    def _classify(self, category):
        img_path = self.images[self.current_index]

        if self.retesting_ovrigt and category == "Övrigt":
            # Already in the Övrigt folder — nothing to do, just advance
            self.current_index += 1
            self.show_classify_screen()
            return

        # Record result for CSV mode
        if self.csv_mode:
            meta = self.csv_data[self.current_index]
            self.results.append({
                "article_number": meta["article_number"],
                "url": meta["url"],
                "category": category,
            })

        dest_dir = Path(f"{self.test_name}.{category}")
        dest_dir.mkdir(exist_ok=True)

        if self.csv_mode:
            meta = self.csv_data[self.current_index]
            suffix = img_path.suffix or ".jpg"
            base_name = f"{meta['article_number']}{suffix}"
        else:
            base_name = img_path.name

        dest = dest_dir / base_name
        if dest.exists():
            stem = Path(base_name).stem
            suffix = Path(base_name).suffix
            counter = 1
            while dest.exists():
                dest = dest_dir / f"{stem}_{counter}{suffix}"
                counter += 1

        if self.retesting_ovrigt:
            shutil.move(str(img_path), dest)
        else:
            shutil.copy2(img_path, dest)

        self.current_index += 1
        self.show_classify_screen()

    def _add_category_during_test(self):
        if len(self.categories) >= 9:
            messagebox.showwarning("Max antal", "Du kan ha max 9 kategorier (tangenterna 1–9).")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Lägg till kategori")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.configure(bg="#f5f5f5")

        self.root.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() // 2 - 180
        y = self.root.winfo_y() + self.root.winfo_height() // 2 - 70
        dialog.geometry(f"360x140+{x}+{y}")

        tk.Label(dialog, text="Namn på ny kategori:", font=("Segoe UI", 12),
                 bg="#f5f5f5").pack(pady=(20, 6))

        var = tk.StringVar()
        entry = tk.Entry(dialog, textvariable=var, font=("Segoe UI", 12),
                         width=26, relief="solid", bd=1)
        entry.pack(ipady=5)
        entry.focus()

        def confirm():
            name = var.get().strip()
            if not name:
                return
            if name in self.categories or name == "Övrigt":
                messagebox.showwarning("Dubblett", f'Kategorin "{name}" finns redan.', parent=dialog)
                return
            self.categories.append(name)
            dialog.destroy()
            self.show_classify_screen()

        entry.bind("<Return>", lambda _: confirm())
        entry.bind("<Escape>", lambda _: dialog.destroy())
        self.make_btn(dialog, "Lägg till", confirm, bg="#4CAF50", bold=True).pack(pady=10)

    def _skip(self):
        self.current_index += 1
        self.show_classify_screen()

    def _confirm_end(self):
        if messagebox.askyesno("Avsluta test", "Vill du avsluta testet?"):
            self.show_done_screen()

    # ----------------------------------------------- screen 4: done

    def show_done_screen(self):
        self.clear()

        frame = tk.Frame(self.root, bg="#f5f5f5")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(frame, text="✓ Test avslutat!", font=("Segoe UI", 24, "bold"),
                 bg="#f5f5f5", fg="#4CAF50").pack(pady=(0, 20))

        tk.Label(frame, text=f"Test: {self.test_name}", font=("Segoe UI", 13),
                 bg="#f5f5f5").pack()
        tk.Label(frame, text=f"Behandlade bilder: {self.current_index}",
                 font=("Segoe UI", 12), bg="#f5f5f5", fg="#555").pack(pady=(4, 16))

        # Summary of saved folders
        tk.Label(frame, text="Sparade mappar:", font=("Segoe UI", 11, "bold"),
                 bg="#f5f5f5").pack(anchor="w")

        for cat in self.categories + ["Övrigt"]:
            folder = Path(f"{self.test_name}.{cat}")
            if folder.exists():
                count = len(list(folder.iterdir()))
                tk.Label(frame, text=f"  📁  {folder.name}  —  {count} bild(er)",
                         font=("Segoe UI", 11), bg="#f5f5f5", fg="#444").pack(anchor="w")

        btn_row = tk.Frame(frame, bg="#f5f5f5", pady=20)
        btn_row.pack()

        # Excel export — only in CSV mode with results
        if self.csv_mode and self.results:
            self.make_btn(btn_row, "💾  Exportera Excel", self._export_excel,
                          bg="#1B5E20", font_size=12, bold=True).pack(fill=tk.X, pady=(0, 10))

        ovrigt_dir = Path(f"{self.test_name}.Övrigt")
        ovrigt_images = sorted(
            [f for f in ovrigt_dir.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS]
        ) if ovrigt_dir.exists() else []

        if ovrigt_images:
            self.make_btn(btn_row, f"Testa Övrigt igen  ({len(ovrigt_images)} bilder)",
                          self._retest_ovrigt, bg="#FF9800", bold=True).pack(fill=tk.X, pady=(0, 10))

        nav_row = tk.Frame(btn_row, bg="#f5f5f5")
        nav_row.pack()
        self.make_btn(nav_row, "Nytt test", self.show_name_screen,
                      bg="#2196F3", bold=True).pack(side=tk.LEFT, padx=8)
        self.make_btn(nav_row, "Avsluta program", self.root.quit,
                      bg="#e53935").pack(side=tk.LEFT, padx=8)

    # ----------------------------------------------- Excel export

    def _export_excel(self):
        if not OPENPYXL_AVAILABLE:
            messagebox.showerror(
                "openpyxl saknas",
                "Installera openpyxl för att exportera Excel:\n  pip install openpyxl"
            )
            return

        save_path = filedialog.asksaveasfilename(
            title="Spara Excel-fil",
            defaultextension=".xlsx",
            initialfile=f"{self.test_name}_resultat.xlsx",
            filetypes=[("Excel-filer", "*.xlsx"), ("Alla filer", "*.*")]
        )
        if not save_path:
            return

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Resultat"

        # Header
        ws.append(["Artikelnummer", "Kategori", "URL"])
        for row in self.results:
            ws.append([row["article_number"], row["category"], row["url"]])

        # Column widths
        ws.column_dimensions["A"].width = 20
        ws.column_dimensions["B"].width = 20
        ws.column_dimensions["C"].width = 60

        try:
            wb.save(save_path)
            messagebox.showinfo("Exporterat", f"Excel-filen sparades:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Fel", f"Kunde inte spara filen:\n{e}")

    # ----------------------------------------------- re-test Övrigt

    def _retest_ovrigt(self):
        ovrigt_dir = Path(f"{self.test_name}.Övrigt")
        images = sorted(
            [f for f in ovrigt_dir.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS]
        )
        if not images:
            messagebox.showinfo("Inga bilder", "Det finns inga bilder i Övrigt-mappen.")
            return
        self.images = images
        self.current_index = 0
        self.retesting_ovrigt = True
        self.show_classify_screen()


# ------------------------------------------------------------------ entry point

if __name__ == "__main__":
    missing = []
    if not PIL_AVAILABLE:
        missing.append("Pillow  →  pip install pillow")
    if not OPENPYXL_AVAILABLE:
        missing.append("openpyxl  →  pip install openpyxl")

    if missing:
        import tkinter.messagebox as mb
        import tkinter as _tk
        _r = _tk.Tk()
        _r.withdraw()
        mb.showwarning(
            "Paket saknas",
            "Följande paket saknas:\n\n" + "\n".join(missing) +
            "\n\nProgrammet startar ändå men vissa funktioner är begränsade."
        )
        _r.destroy()

    root = tk.Tk()
    app = ImageClassifierApp(root)
    root.mainloop()
