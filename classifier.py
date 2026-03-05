import tkinter as tk
from tkinter import messagebox, filedialog
import csv
import os
import shutil
import tempfile
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
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
CATEGORY_COLORS = ["#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#00BCD4", "#E91E63"]


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

        self.show_name_screen()

    # ------------------------------------------------------------------ helpers

    def clear(self):
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
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir = None

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
        tk.Label(frame, text="Välj om bilderna ska hämtas från lokal mapp eller från en CSV-fil.",
                 font=("Segoe UI", 10), bg="#f5f5f5", fg="#666").pack(pady=(0, 28))

        self.make_btn(frame, "📁  Från mapp  (bilder/)", self._load_images,
                      bg="#2196F3", font_size=13, bold=True).pack(fill=tk.X, pady=6, ipady=4)

        self.make_btn(frame, "📄  Ladda upp CSV-fil", self._load_csv,
                      bg="#7B1FA2", font_size=13, bold=True).pack(fill=tk.X, pady=6, ipady=4)

        self.make_btn(frame, "← Tillbaka", self.show_categories_screen,
                      bg="#9e9e9e", font_size=10).pack(pady=(18, 0))

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

        self.images = sorted(
            [f for f in IMAGE_DIR.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS]
        )

        if not self.images:
            messagebox.showwarning(
                "Inga bilder",
                f"Inga bilder hittades i mappen \"{IMAGE_DIR}\".\n"
                "Stödda format: jpg, jpeg, png, gif, bmp, webp, tiff"
            )
            return

        self.current_index = 0
        self.show_classify_screen()

    # ---------------------------------------------------------- load images (CSV)

    def _load_csv(self):
        path = filedialog.askopenfilename(
            title="Välj CSV-fil",
            filetypes=[("CSV-filer", "*.csv"), ("Alla filer", "*.*")]
        )
        if not path:
            return

        # Parse CSV — col 0 = article number, col 3 = image URL
        rows = []
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for line_no, row in enumerate(reader, 1):
                    if len(row) < 4:
                        continue
                    article = row[0].strip()
                    url = row[3].strip()
                    if not article or not url:
                        continue
                    # Skip header-like rows where col 3 doesn't look like a URL
                    if line_no == 1 and not url.lower().startswith("http"):
                        continue
                    rows.append({"article_number": article, "url": url})
        except Exception as e:
            messagebox.showerror("CSV-fel", f"Kunde inte läsa CSV-filen:\n{e}")
            return

        if not rows:
            messagebox.showwarning("Inga rader", "Inga giltiga rader hittades i CSV-filen.\n"
                                   "Kontrollera att kolumn 1 är artikelnummer och kolumn 4 är URL.")
            return

        self._download_csv_images(rows)

    def _download_csv_images(self, rows):
        """Download images from URLs in rows and set up for classification."""
        self.clear()

        # Progress screen
        hdr = tk.Frame(self.root, bg="#333", pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"Test: {self.test_name}", font=("Segoe UI", 12, "bold"),
                 bg="#333", fg="white").pack(side=tk.LEFT, padx=20)

        frame = tk.Frame(self.root, bg="#f5f5f5")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(frame, text="Hämtar bilder…", font=("Segoe UI", 16, "bold"),
                 bg="#f5f5f5").pack(pady=(0, 16))

        progress_lbl = tk.Label(frame, text="", font=("Segoe UI", 11),
                                bg="#f5f5f5", fg="#555", width=50)
        progress_lbl.pack()

        counter_lbl = tk.Label(frame, text="", font=("Segoe UI", 10),
                               bg="#f5f5f5", fg="#888")
        counter_lbl.pack(pady=(6, 0))

        self.root.update()

        self.temp_dir = tempfile.mkdtemp(prefix="bildklassificering_")
        downloaded = []
        failed = 0

        for i, row in enumerate(rows):
            progress_lbl.configure(text=f"Hämtar: {row['url'][:55]}…")
            counter_lbl.configure(text=f"{i + 1} / {len(rows)}")
            self.root.update()

            url = row["url"]
            # Derive a filename from URL; fall back to numbered name
            url_path = url.split("?")[0].rstrip("/")
            filename = url_path.split("/")[-1] or f"img_{i + 1}"
            # Ensure there's an extension
            if "." not in Path(filename).suffix:
                filename += ".jpg"

            dest = Path(self.temp_dir) / f"{i:05d}_{filename}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    with open(dest, "wb") as out:
                        out.write(resp.read())
                downloaded.append({
                    "article_number": row["article_number"],
                    "url": url,
                    "img_path": dest,
                })
            except Exception:
                failed += 1

        if not downloaded:
            messagebox.showerror("Fel", "Inga bilder kunde laddas ner.\n"
                                 "Kontrollera att URL:erna i CSV-filen är korrekta.")
            self.show_source_screen()
            return

        self.csv_mode = True
        self.csv_data = downloaded
        self.images = [d["img_path"] for d in downloaded]
        self.results = []
        self.current_index = 0

        if failed:
            messagebox.showwarning(
                "Varning",
                f"{failed} bild(er) kunde inte laddas ner och hoppas över."
            )

        self.show_classify_screen()

    # ----------------------------------------------- screen 3: classify

    def show_classify_screen(self):
        self.clear()

        if self.current_index >= len(self.images):
            self.show_done_screen()
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

        # ── Image area
        img_area = tk.Frame(self.root, bg="#1a1a1a")
        img_area.pack(fill=tk.BOTH, expand=True)

        self.img_label = tk.Label(img_area, bg="#1a1a1a")
        self.img_label.pack(expand=True, pady=8)
        self._display_image(img_path)

        # ── Filename / article number
        if self.csv_mode:
            meta = self.csv_data[self.current_index]
            info_text = f"Artikel: {meta['article_number']}   |   {img_path.name}"
        else:
            info_text = img_path.name
        tk.Label(self.root, text=info_text, font=("Segoe UI", 9),
                 bg="#f5f5f5", fg="#999").pack(pady=(4, 0))

        # ── Category buttons
        cat_frame = tk.Frame(self.root, bg="#f5f5f5", pady=10)
        cat_frame.pack(fill=tk.X, padx=16)

        inner = tk.Frame(cat_frame, bg="#f5f5f5")
        inner.pack()

        for i, cat in enumerate(self.categories):
            color = CATEGORY_COLORS[i % len(CATEGORY_COLORS)]
            self.make_btn(inner, cat, lambda c=cat: self._classify(c),
                          bg=color, bold=True, width=12).pack(side=tk.LEFT, padx=4)

        self.make_btn(inner, "Övrigt", lambda: self._classify("Övrigt"),
                      bg="#757575", width=10).pack(side=tk.LEFT, padx=4)

        # ── Control row
        ctrl = tk.Frame(self.root, bg="#f5f5f5", pady=6)
        ctrl.pack(fill=tk.X, padx=16)

        self.make_btn(ctrl, "Hoppa över", self._skip,
                      bg="#e0e0e0", fg="#333", font_size=10).pack(side=tk.LEFT)
        self.make_btn(ctrl, "Avsluta test", self._confirm_end,
                      bg="#e53935", font_size=10).pack(side=tk.RIGHT)

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
