import tkinter as tk
from tkinter import messagebox
import os
import shutil
from pathlib import Path

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

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

    # ---------------------------------------------------------- screen 1: name

    def show_name_screen(self):
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
        # Sanitise for use as folder prefix
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

        # Header
        hdr = tk.Frame(self.root, bg="#333", pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"Test: {self.test_name}", font=("Segoe UI", 12, "bold"),
                 bg="#333", fg="white").pack(side=tk.LEFT, padx=20)

        # Body
        body = tk.Frame(self.root, bg="#f5f5f5", padx=40, pady=20)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(body, text="Kategorier", font=("Segoe UI", 16, "bold"),
                 bg="#f5f5f5").pack(anchor="w", pady=(0, 4))
        tk.Label(body, text="Skriv en kategori per rad. Knappen \"Övrigt\" läggs alltid till automatiskt.",
                 font=("Segoe UI", 10), bg="#f5f5f5", fg="#666").pack(anchor="w", pady=(0, 12))

        # Scrollable list of entries
        self.entries_frame = tk.Frame(body, bg="#f5f5f5")
        self.entries_frame.pack(fill=tk.X)

        for _ in range(3):
            self._add_category_row()

        # Buttons row
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
        visible = [e for e in self.category_entries]
        for i, e in enumerate(visible):
            # Each entry's parent row has a label as first child
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
        self._load_images()

    # ---------------------------------------------------------- load images

    def _load_images(self):
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

        # ── Filename
        tk.Label(self.root, text=img_path.name, font=("Segoe UI", 9),
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

        # Always-present "Övrigt" button
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
                # Only works reliably for PNG/GIF without Pillow
                self.photo = tk.PhotoImage(file=str(path))
            self.img_label.configure(image=self.photo, text="")
        except Exception as e:
            self.img_label.configure(image="", text=f"Kunde inte visa bild:\n{e}",
                                     fg="white", font=("Segoe UI", 11))

    def _classify(self, category):
        img_path = self.images[self.current_index]
        dest_dir = Path(f"{self.test_name}.{category}")
        dest_dir.mkdir(exist_ok=True)

        dest = dest_dir / img_path.name
        if dest.exists():
            stem, suffix = img_path.stem, img_path.suffix
            counter = 1
            while dest.exists():
                dest = dest_dir / f"{stem}_{counter}{suffix}"
                counter += 1

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

        btn_row = tk.Frame(frame, bg="#f5f5f5", pady=28)
        btn_row.pack()

        self.make_btn(btn_row, "Nytt test", self.show_name_screen,
                      bg="#2196F3", bold=True).pack(side=tk.LEFT, padx=8)
        self.make_btn(btn_row, "Avsluta program", self.root.quit,
                      bg="#e53935").pack(side=tk.LEFT, padx=8)


# ------------------------------------------------------------------ entry point

if __name__ == "__main__":
    if not PIL_AVAILABLE:
        import tkinter.messagebox as mb
        import tkinter as _tk
        _r = _tk.Tk()
        _r.withdraw()
        mb.showwarning(
            "Pillow saknas",
            "Pillow är inte installerat.\n"
            "Kör:  pip install pillow\n\n"
            "Programmet startar ändå men kan bara visa PNG/GIF."
        )
        _r.destroy()

    root = tk.Tk()
    app = ImageClassifierApp(root)
    root.mainloop()
