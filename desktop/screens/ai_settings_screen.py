"""AISettingsScreen — user configures the AI model and API settings."""
from typing import Dict

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QRadioButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from core.constants import DEFAULT_AI_URL, DEFAULT_MODEL, DEFAULT_EXTERNAL_PROVIDERS
from desktop.widgets.header_bar import HeaderBar
from desktop.widgets.helpers import mk_btn, sep


class AISettingsScreen(QWidget):
    go_next = pyqtSignal(dict)  # {model, api_url, compress_images, api_key} or {} to skip AI
    go_back = pyqtSignal()

    def __init__(self, test_name: str, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(HeaderBar(test_name))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        center = QWidget()
        c = QVBoxLayout(center)
        c.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setStyleSheet("background-color:#313244; border-radius:12px;")
        card.setFixedWidth(500)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(36, 36, 36, 36)
        cl.setSpacing(10)

        title = QLabel("AI-inställningar")
        title.setStyleSheet("font-size:22px; font-weight:bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(title)

        sub = QLabel("Välj mellan lokal LLM eller extern API-leverantör.")
        sub.setStyleSheet("color:#6c7086; font-size:12px;")
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(sub)
        cl.addSpacing(8)

        # ── Provider toggle ──────────────────────────────────────────────
        self._provider_group = QButtonGroup(self)
        provider_row = QHBoxLayout()
        provider_row.setSpacing(8)

        self._rb_local = QRadioButton("Lokal (LM Studio)")
        self._rb_local.setChecked(True)
        self._rb_external = QRadioButton("Extern API")
        self._provider_group.addButton(self._rb_local, 0)
        self._provider_group.addButton(self._rb_external, 1)
        provider_row.addWidget(self._rb_local)
        provider_row.addWidget(self._rb_external)
        provider_row.addStretch()
        cl.addLayout(provider_row)
        cl.addWidget(sep())

        # ── Local settings ───────────────────────────────────────────────
        self._local_frame = QFrame()
        self._local_frame.setStyleSheet("background:transparent;")
        lf = QVBoxLayout(self._local_frame)
        lf.setContentsMargins(0, 0, 0, 0)
        lf.setSpacing(8)
        lf.addWidget(QLabel("LM Studio URL:"))
        self.url_edit = QLineEdit(DEFAULT_AI_URL)
        lf.addWidget(self.url_edit)
        lf.addWidget(QLabel("Modell:"))
        self.model_edit = QLineEdit(DEFAULT_MODEL)
        lf.addWidget(self.model_edit)
        cl.addWidget(self._local_frame)

        # ── External settings ────────────────────────────────────────────
        self._ext_frame = QFrame()
        self._ext_frame.setStyleSheet("background:transparent;")
        self._ext_frame.setVisible(False)
        ef = QVBoxLayout(self._ext_frame)
        ef.setContentsMargins(0, 0, 0, 0)
        ef.setSpacing(8)

        ef.addWidget(QLabel("Leverantör:"))
        self._ext_provider_group = QButtonGroup(self)
        self._ext_provider_buttons: Dict[str, QRadioButton] = {}
        for i, name in enumerate(DEFAULT_EXTERNAL_PROVIDERS):
            rb = QRadioButton(name)
            if i == 0:
                rb.setChecked(True)
            self._ext_provider_group.addButton(rb, i)
            self._ext_provider_buttons[name] = rb
            ef.addWidget(rb)
            rb.toggled.connect(self._on_provider_changed)

        ef.addSpacing(4)
        ef.addWidget(QLabel("API-nyckel:"))
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setPlaceholderText("Klistra in din API-nyckel här")
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        ef.addWidget(self._api_key_edit)

        ef.addWidget(QLabel("API URL (fylls i automatiskt):"))
        self._ext_url_edit = QLineEdit()
        ef.addWidget(self._ext_url_edit)

        ef.addWidget(QLabel("Modell:"))
        self._ext_model_edit = QLineEdit()
        ef.addWidget(self._ext_model_edit)
        cl.addWidget(self._ext_frame)

        # ── Common settings ──────────────────────────────────────────────
        cl.addWidget(sep())
        self.compress_cb = QCheckBox("Komprimera bilder (snabbare, marginellt sämre precision)")
        self.compress_cb.setChecked(True)
        cl.addWidget(self.compress_cb)

        cl.addSpacing(8)
        go = mk_btn("Använd AI  →", "#89b4fa", "#1e1e2e", h=44)
        go.clicked.connect(self._go)
        cl.addWidget(go)

        skip = mk_btn("Hoppa över AI", "#45475a", "#cdd6f4")
        skip.clicked.connect(lambda: self.go_next.emit({}))
        cl.addWidget(skip)

        back = mk_btn("← Tillbaka", "#45475a", "#cdd6f4")
        back.clicked.connect(self.go_back.emit)
        cl.addWidget(back)

        c.addWidget(card)
        scroll.setWidget(center)
        outer.addWidget(scroll)

        self._rb_local.toggled.connect(self._toggle_provider)
        self._on_provider_changed()

    def _toggle_provider(self, local_checked: bool) -> None:
        self._local_frame.setVisible(local_checked)
        self._ext_frame.setVisible(not local_checked)

    def _on_provider_changed(self) -> None:
        for name, rb in self._ext_provider_buttons.items():
            if rb.isChecked():
                info = DEFAULT_EXTERNAL_PROVIDERS[name]
                self._ext_url_edit.setText(info["url"])
                self._ext_model_edit.setText(info["model"])
                break

    def _go(self) -> None:
        if self._rb_local.isChecked():
            self.go_next.emit({
                "api_url":         self.url_edit.text().strip() or DEFAULT_AI_URL,
                "model":           self.model_edit.text().strip() or DEFAULT_MODEL,
                "compress_images": self.compress_cb.isChecked(),
                "api_key":         "",
            })
        else:
            api_key = self._api_key_edit.text().strip()
            if not api_key:
                QMessageBox.warning(self, "API-nyckel saknas",
                                    "Du måste ange en API-nyckel för extern leverantör.")
                return
            self.go_next.emit({
                "api_url":         self._ext_url_edit.text().strip(),
                "model":           self._ext_model_edit.text().strip(),
                "compress_images": self.compress_cb.isChecked(),
                "api_key":         api_key,
            })
