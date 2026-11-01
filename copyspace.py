from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from copyspace_core import (
    APP_NAME,
    APP_VERSION,
    MAX_IMAGE_PIXELS,
    CopySpaceStore,
    data_directory,
    classify_clipboard_text,
)

THEMES: dict[str, dict[str, str]] = {
    # CopySpace deliberately has its own identity: a calm editorial archive,
    # not the graphite/orange utility look used by SmartFolder.
    "Фарфор": {
        "window": "#F4F2ED", "sidebar": "#EAE7E0", "panel": "#FFFFFF", "panel2": "#F4F2EC",
        "border": "#E1DDD4", "text": "#25283A", "muted": "#7B7D8D", "accent": "#6258D9",
        "accent_hover": "#756BE9", "selection": "#E9E7FB", "input": "#FBFAF7", "danger": "#C94F68",
    },
    "Полночь": {
        "window": "#111522", "sidebar": "#151A2B", "panel": "#1B2235", "panel2": "#242D44",
        "border": "#343E59", "text": "#F0F1FA", "muted": "#A0A8C0", "accent": "#A99BFF",
        "accent_hover": "#BDB2FF", "selection": "#302D51", "input": "#171E30", "danger": "#FF8297",
    },
    "Лаванда": {
        "window": "#F3F0F8", "sidebar": "#EAE5F3", "panel": "#FFFFFF", "panel2": "#F6F3FA",
        "border": "#E2D9EF", "text": "#302941", "muted": "#82778F", "accent": "#8965C7",
        "accent_hover": "#9A78D8", "selection": "#EEE6FA", "input": "#FCFAFF", "danger": "#C94F68",
    },
    "Океан": {
        "window": "#EDF4F7", "sidebar": "#E1EBF0", "panel": "#FFFFFF", "panel2": "#F2F7F9",
        "border": "#D5E2E9", "text": "#203344", "muted": "#718A9A", "accent": "#287EA5",
        "accent_hover": "#3595BD", "selection": "#DDEFF6", "input": "#FAFCFD", "danger": "#C94F68",
    },
    "Мята": {
        "window": "#EEF4F0", "sidebar": "#E3ECE6", "panel": "#FFFFFF", "panel2": "#F3F8F4",
        "border": "#D8E5DC", "text": "#25382F", "muted": "#758B7D", "accent": "#38876A",
        "accent_hover": "#469C7B", "selection": "#DDF0E5", "input": "#FAFDFA", "danger": "#C94F68",
    },
    "Роза": {
        "window": "#F7F0F2", "sidebar": "#F0E5E9", "panel": "#FFFFFF", "panel2": "#FBF5F7",
        "border": "#EBD9E0", "text": "#3E2B35", "muted": "#967C88", "accent": "#C05C83",
        "accent_hover": "#D16F96", "selection": "#F6E2EA", "input": "#FFFBFC", "danger": "#B9435B",
    },
    "Сланец": {
        "window": "#EDEFF3", "sidebar": "#E2E6ED", "panel": "#FFFFFF", "panel2": "#F4F6F9",
        "border": "#D9DEE7", "text": "#293346", "muted": "#778397", "accent": "#526B9B",
        "accent_hover": "#647FAF", "selection": "#E1E8F5", "input": "#FBFCFE", "danger": "#C94F68",
    },
}

# Every palette is available in both light and dark mode. Dark variants retain
# the hue/accent of their light counterpart while changing all surfaces and text.
for _name in list(THEMES.keys()):
    if _name == "Полночь":
        continue
    _base = THEMES[_name]
    THEMES[f"{_name} · тёмная"] = {
        "window": "#111522", "sidebar": "#171D2B", "panel": "#1D2637", "panel2": "#253145",
        "border": "#35445B", "text": "#EEF1F7", "muted": "#A3AEC0",
        "accent": _base["accent"], "accent_hover": _base["accent_hover"],
        "selection": "#30394C", "input": "#182233", "danger": "#FF8297",
    }

LEGACY_THEMES = {
    "Тёмная": "Полночь", "Светлая": "Фарфор", "Изумрудная": "Мята",
    "Amber": "Сланец", "Океан": "Океан", "Аметист": "Лаванда", "Розовая": "Роза",
}


def build_stylesheet(theme_name: str) -> str:
    c = THEMES.get(theme_name, THEMES["Фарфор"])
    return f"""
    * {{ font-family: 'Segoe UI Variable', 'Segoe UI', 'Arial'; font-size: 10pt; }}
    QMainWindow, QWidget#root {{ background: {c['window']}; color: {c['text']}; }}
    QWidget {{ color: {c['text']}; }}

    QFrame#appHeader {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 22px; }}
    QFrame#navBar {{ background: {c['sidebar']}; border: 1px solid {c['border']}; border-radius: 17px; }}
    QFrame#summaryCard {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 17px; }}
    QFrame#listPanel {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 21px; }}
    QFrame#detailPanel {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 21px; }}
    QFrame#settingsCard {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 19px; }}
    QFrame#captureCard {{ background: {c['panel2']}; border: 1px solid {c['border']}; border-radius: 15px; }}
    QFrame#sideDivider {{ background: {c['border']}; border: none; max-height: 1px; min-height: 1px; }}

    QLabel#brandMark {{ background: {c['accent']}; color: #FFFFFF; border-radius: 14px; font-size: 15pt; font-weight: 900; }}
    QLabel#brandName {{ font-size: 17pt; font-weight: 850; letter-spacing: -0.6px; }}
    QLabel#brandSub {{ color: {c['muted']}; font-size: 7pt; font-weight: 800; letter-spacing: 1.7px; }}
    QLabel#eyebrow {{ color: {c['muted']}; font-size: 8pt; font-weight: 850; letter-spacing: 1.6px; }}
    QLabel#sectionLabel {{ color: {c['muted']}; font-size: 8pt; font-weight: 850; letter-spacing: 1.3px; }}
    QLabel#pageTitle {{ font-size: 27pt; font-weight: 850; letter-spacing: -1.0px; }}
    QLabel#pageSubtitle {{ color: {c['muted']}; font-size: 9.5pt; }}
    QLabel#muted {{ color: {c['muted']}; }}
    QLabel#statusLabel {{ color: {c['muted']}; font-size: 8.5pt; padding: 2px 4px; }}
    QLabel#statValue {{ font-size: 19pt; font-weight: 850; letter-spacing: -0.7px; }}
    QLabel#statCaption {{ color: {c['muted']}; font-size: 8pt; font-weight: 700; }}
    QLabel#statGlyph {{ color: {c['accent']}; font-size: 15pt; font-weight: 900; }}
    QLabel#captureState {{ color: {c['muted']}; font-size: 8pt; font-weight: 700; }}
    QLabel#countPill {{ background: {c['selection']}; color: {c['accent']}; border-radius: 10px; padding: 4px 9px; font-weight: 850; }}

    QPushButton {{
        background: {c['panel2']}; color: {c['text']}; border: 1px solid {c['border']};
        border-radius: 12px; padding: 9px 13px; min-height: 18px; font-weight: 650;
    }}
    QPushButton:hover {{ border-color: {c['accent']}; background: {c['selection']}; }}
    QPushButton:pressed {{ background: {c['accent']}; color: #FFFFFF; }}
    QPushButton#primaryButton {{ background: {c['accent']}; color: #FFFFFF; border: none; font-weight: 850; }}
    QPushButton#primaryButton:hover {{ background: {c['accent_hover']}; }}
    QPushButton#dangerButton {{ color: {c['danger']}; }}
    QPushButton#navButton {{ text-align: center; background: transparent; border: 1px solid transparent; padding: 10px 15px; color: {c['muted']}; border-radius: 12px; font-weight: 700; min-height: 19px; }}
    QPushButton#navButton:hover {{ background: {c['panel']}; color: {c['text']}; }}
    QPushButton#navButton:checked {{ background: {c['panel']}; border-color: {c['border']}; color: {c['accent']}; font-weight: 850; }}
    QPushButton#captureButton {{ background: {c['selection']}; color: {c['accent']}; border: 1px solid {c['border']}; border-radius: 13px; font-weight: 850; padding-left: 15px; padding-right: 15px; }}
    QPushButton#captureButton[active="true"] {{ background: {c['accent']}; color: #FFFFFF; border-color: {c['accent']}; }}
    QPushButton#iconButton {{ padding: 8px; min-width: 24px; max-width: 38px; }}

    QLineEdit, QComboBox, QPlainTextEdit {{
        background: {c['input']}; color: {c['text']}; border: 1px solid {c['border']};
        border-radius: 12px; padding: 10px 13px; selection-background-color: {c['accent']};
    }}
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {c['accent']}; }}
    QLineEdit#searchInput {{ border-radius: 14px; padding: 12px 16px; min-height: 21px; font-size: 10pt; }}
    QComboBox#collectionFilter {{ min-width: 170px; padding: 9px 12px; }}
    QComboBox::drop-down {{ border: none; width: 25px; }}

    QListWidget {{ background: transparent; border: none; outline: none; padding: 7px; }}
    QListWidget::item {{ background: transparent; border: none; padding: 0px; margin: 4px 1px; }}
    QListWidget::item:selected {{ background: transparent; }}
    QFrame#clipCard {{ background: {c['panel2']}; border: 1px solid transparent; border-radius: 16px; }}
    QFrame#clipCard[selected="true"] {{ background: {c['selection']}; border: 1px solid {c['accent']}; }}
    QLabel#clipKind {{ color: {c['accent']}; font-size: 7.5pt; font-weight: 900; letter-spacing: 1px; }}
    QLabel#clipPreview {{ color: {c['text']}; font-size: 10pt; font-weight: 650; }}
    QLabel#clipMeta {{ color: {c['muted']}; font-size: 8pt; }}
    QLabel#kindIcon {{ background: {c['selection']}; color: {c['accent']}; border-radius: 13px; font-size: 13pt; font-weight: 900; }}
    QPlainTextEdit#previewText {{ border: 1px solid {c['border']}; border-radius: 15px; padding: 14px; font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 9.5pt; }}
    QSplitter::handle {{ background: transparent; width: 12px; }}

    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 5px 2px; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; min-height: 36px; border-radius: 4px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['accent']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; background: transparent; border: none; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px 5px; }}
    QScrollBar::handle:horizontal {{ background: {c['border']}; min-width: 36px; border-radius: 4px; }}
    QScrollBar::handle:horizontal:hover {{ background: {c['accent']}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; background: transparent; border: none; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
    QDialog {{ background: {c['window']}; }}
    """


def pretty_size(size: int) -> str:
    value = float(max(0, size))
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or unit == "ГБ":
            return f"{value:.1f} {unit}" if unit != "Б" else f"{int(value)} Б"
        value /= 1024
    return f"{value:.1f} ГБ"


def pretty_date(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%d.%m.%Y · %H:%M")
    except Exception:
        return value


class CopySpaceWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1280, 820)
        self.setMinimumSize(1050, 680)
        self.store = CopySpaceStore()
        self.clipboard = QGuiApplication.clipboard()
        self._clipboard_capture_timer = QTimer(self)
        self._clipboard_capture_timer.setSingleShot(True)
        self._clipboard_capture_timer.setInterval(120)
        self._clipboard_capture_timer.timeout.connect(lambda: self._capture_clipboard(manual=False))
        self.scope = "all"
        self.category_filter: str | None = None
        self.current_clip_id: int | None = None
        self.current_page = "history"
        self.capture_enabled = self.store.get_setting("capture_enabled", "0") == "1"
        stored_theme = self.store.get_setting("theme", "Фарфор")
        self.theme_name = LEGACY_THEMES.get(stored_theme, stored_theme)
        if self.theme_name not in THEMES:
            self.theme_name = "Фарфор"
        if stored_theme != self.theme_name:
            self.store.set_setting("theme", self.theme_name)

        self._build_ui()
        self._set_nav_checked("all")
        self._apply_theme()
        self.clipboard.dataChanged.connect(self._on_clipboard_changed)
        self._refresh_categories()
        self._update_capture_button()
        self.refresh_history()
        self._set_status("Захват приостановлен. Включи его, чтобы сохранять новые элементы буфера обмена." if not self.capture_enabled else "Захват буфера обмена включён.")

        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search_input.setFocus)
        QShortcut(QKeySequence("Ctrl+Shift+V"), self, activated=self.capture_current_clipboard)
        QShortcut(QKeySequence("Delete"), self, activated=self.delete_selected)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 18, 22, 14)
        outer.setSpacing(12)
        self.setCentralWidget(root)

        # New CopySpace composition: a wide command header, horizontal library
        # navigation, an overview strip, and a two-pane archive workspace.
        app_header = QFrame()
        app_header.setObjectName("appHeader")
        header = QHBoxLayout(app_header)
        header.setContentsMargins(19, 13, 18, 13)
        header.setSpacing(13)

        brand_mark = QLabel("CS")
        brand_mark.setObjectName("brandMark")
        brand_mark.setFixedSize(48, 48)
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(brand_mark)

        brand_col = QVBoxLayout()
        brand_col.setContentsMargins(0, 0, 10, 0)
        brand_col.setSpacing(1)
        brand_name = QLabel("CopySpace")
        brand_name.setObjectName("brandName")
        brand_sub = QLabel("YOUR PERSONAL CLIPBOARD")
        brand_sub.setObjectName("brandSub")
        brand_col.addWidget(brand_name)
        brand_col.addWidget(brand_sub)
        header.addLayout(brand_col)
        header.addStretch(1)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("⌕   Поиск по библиотеке…  Ctrl + F")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(230)
        self.search_input.setMaximumWidth(390)
        self.search_input.textChanged.connect(self.refresh_history)
        header.addWidget(self.search_input, 2)

        capture_col = QVBoxLayout()
        capture_col.setSpacing(2)
        capture_col.setContentsMargins(0, 0, 0, 0)
        self.capture_button = QPushButton()
        self.capture_button.setObjectName("captureButton")
        self.capture_button.clicked.connect(self.toggle_capture)
        capture_col.addWidget(self.capture_button)
        self.capture_state_label = QLabel("ЛОКАЛЬНЫЙ ЗАХВАТ")
        self.capture_state_label.setObjectName("captureState")
        self.capture_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        capture_col.addWidget(self.capture_state_label)
        header.addLayout(capture_col)

        self.capture_now_button = QPushButton("＋  Сохранить сейчас")
        self.capture_now_button.setObjectName("primaryButton")
        self.capture_now_button.setMinimumHeight(43)
        self.capture_now_button.setToolTip("Добавить текущее содержимое буфера вручную")
        self.capture_now_button.clicked.connect(self.capture_current_clipboard)
        header.addWidget(self.capture_now_button)
        outer.addWidget(app_header)

        nav_bar = QFrame()
        nav_bar.setObjectName("navBar")
        nav = QHBoxLayout(nav_bar)
        nav.setContentsMargins(8, 6, 8, 6)
        nav.setSpacing(4)
        self.nav_buttons: dict[str, QPushButton] = {}
        self._add_nav(nav, "all", "▤  Все записи", self._show_all)
        self._add_nav(nav, "favorites", "☆  Избранное", self._show_favorites)
        self._add_nav(nav, "text", "T  Текст", self._show_text)
        self._add_nav(nav, "links", "↗  Ссылки", self._show_links)
        self._add_nav(nav, "images", "▧  Изображения", self._show_images)
        nav.addSpacing(10)
        collection_caption = QLabel("КОЛЛЕКЦИЯ")
        collection_caption.setObjectName("sectionLabel")
        nav.addWidget(collection_caption)
        self.category_filter_combo = QComboBox()
        self.category_filter_combo.setObjectName("collectionFilter")
        self.category_filter_combo.addItem("Все коллекции")
        self.category_filter_combo.currentTextChanged.connect(self._collection_filter_changed)
        nav.addWidget(self.category_filter_combo)
        nav.addStretch(1)
        self._add_nav(nav, "settings", "⚙  Настройки", self.show_settings)
        outer.addWidget(nav_bar)

        hero = QWidget()
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(3, 8, 3, 0)
        hero_layout.setSpacing(10)
        hero_col = QVBoxLayout()
        hero_col.setSpacing(3)
        self.page_eyebrow = QLabel("PERSONAL SPACE  /  CLIPBOARD")
        self.page_eyebrow.setObjectName("eyebrow")
        self.page_title = QLabel("Моя библиотека")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("Сохранённые фрагменты — в одном спокойном и удобном месте.")
        self.page_subtitle.setObjectName("pageSubtitle")
        hero_col.addWidget(self.page_eyebrow)
        hero_col.addWidget(self.page_title)
        hero_col.addWidget(self.page_subtitle)
        hero_layout.addLayout(hero_col, 1)
        outer.addWidget(hero)

        # Compact overview cards make the screen feel like an archive dashboard.
        self.overview_widget = QWidget()
        overview = QHBoxLayout(self.overview_widget)
        overview.setContentsMargins(0, 0, 0, 0)
        overview.setSpacing(10)
        self.stat_total_value = QLabel("0")
        self.stat_text_value = QLabel("0")
        self.stat_image_value = QLabel("0")
        self.stat_size_value = QLabel("0 Б")
        for glyph, value_label, caption in (
            ("▤", self.stat_total_value, "ВСЕГО ЗАПИСЕЙ"),
            ("T", self.stat_text_value, "ТЕКСТОВЫХ ФРАГМЕНТОВ"),
            ("▧", self.stat_image_value, "ИЗОБРАЖЕНИЙ"),
            ("◫", self.stat_size_value, "МЕСТО В АРХИВЕ"),
        ):
            card = QFrame()
            card.setObjectName("summaryCard")
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(15, 10, 15, 10)
            card_layout.setSpacing(11)
            glyph_label = QLabel(glyph)
            glyph_label.setObjectName("statGlyph")
            glyph_label.setFixedWidth(24)
            glyph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(glyph_label)
            value_col = QVBoxLayout()
            value_col.setSpacing(0)
            value_label.setObjectName("statValue")
            caption_label = QLabel(caption)
            caption_label.setObjectName("statCaption")
            value_col.addWidget(value_label)
            value_col.addWidget(caption_label)
            card_layout.addLayout(value_col, 1)
            overview.addWidget(card, 1)
        outer.addWidget(self.overview_widget)

        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        self.history_page = QWidget()
        history_layout = QVBoxLayout(self.history_page)
        history_layout.setContentsMargins(0, 2, 0, 0)
        history_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(9)

        list_panel = QFrame()
        list_panel.setObjectName("listPanel")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(17, 15, 15, 13)
        list_layout.setSpacing(7)
        list_head = QHBoxLayout()
        list_title = QLabel("НЕДАВНО СОХРАНЁННОЕ")
        list_title.setObjectName("eyebrow")
        list_head.addWidget(list_title)
        list_head.addStretch(1)
        self.clip_count_label = QLabel("0")
        self.clip_count_label.setObjectName("countPill")
        list_head.addWidget(self.clip_count_label)
        list_layout.addLayout(list_head)
        self.stats_label = QLabel("")
        self.stats_label.setObjectName("muted")
        self.stats_label.setStyleSheet("font-size: 8.5pt; padding: 0 2px 5px 2px;")
        list_layout.addWidget(self.stats_label)
        self.clip_list = QListWidget()
        self.clip_list.setSpacing(3)
        self.clip_list.currentItemChanged.connect(self._on_selection_changed)
        list_layout.addWidget(self.clip_list, 1)
        splitter.addWidget(list_panel)

        self.detail_panel = QFrame()
        self.detail_panel.setObjectName("detailPanel")
        self.detail_panel.setMinimumWidth(300)
        self.detail_panel.setMaximumWidth(480)
        detail = QVBoxLayout(self.detail_panel)
        detail.setContentsMargins(20, 19, 20, 18)
        detail.setSpacing(11)
        detail_top = QHBoxLayout()
        detail_title = QLabel("ПРЕДПРОСМОТР")
        detail_title.setObjectName("eyebrow")
        detail_top.addWidget(detail_title)
        detail_top.addStretch(1)
        detail_top.addWidget(QLabel("⌘  DETAILS"))
        detail.addLayout(detail_top)
        self.detail_kind = QLabel("Выбери запись")
        self.detail_kind.setStyleSheet("font-size: 17pt; font-weight: 850;")
        detail.addWidget(self.detail_kind)
        self.detail_meta = QLabel("Здесь появятся свойства и содержимое выбранного фрагмента.")
        self.detail_meta.setObjectName("muted")
        self.detail_meta.setWordWrap(True)
        detail.addWidget(self.detail_meta)
        preview_label = QLabel("СОДЕРЖИМОЕ ФРАГМЕНТА")
        preview_label.setObjectName("sectionLabel")
        detail.addWidget(preview_label)
        self.preview_text = QPlainTextEdit()
        self.preview_text.setObjectName("previewText")
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("Выбери запись слева, чтобы посмотреть её содержимое")
        detail.addWidget(self.preview_text, 1)
        self.preview_image = QLabel()
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setMinimumHeight(160)
        self.preview_image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_image.hide()
        detail.addWidget(self.preview_image, 1)

        category_label = QLabel("ПОМЕСТИТЬ В КОЛЛЕКЦИЮ")
        category_label.setObjectName("sectionLabel")
        detail.addWidget(category_label)
        self.detail_category = QComboBox()
        self.detail_category.currentTextChanged.connect(self._change_category)
        detail.addWidget(self.detail_category)

        action_row1 = QHBoxLayout()
        self.copy_button = QPushButton("Скопировать фрагмент")
        self.copy_button.setObjectName("primaryButton")
        self.copy_button.clicked.connect(self.copy_selected)
        action_row1.addWidget(self.copy_button, 1)
        self.favorite_button = QPushButton("☆")
        self.favorite_button.setFixedWidth(48)
        self.favorite_button.setToolTip("Добавить в избранное")
        self.favorite_button.clicked.connect(self.toggle_favorite)
        action_row1.addWidget(self.favorite_button)
        detail.addLayout(action_row1)

        action_row2 = QHBoxLayout()
        self.pin_button = QPushButton("Закрепить")
        self.pin_button.clicked.connect(self.toggle_pin)
        action_row2.addWidget(self.pin_button, 1)
        self.delete_button = QPushButton("Удалить")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.clicked.connect(self.delete_selected)
        action_row2.addWidget(self.delete_button, 1)
        detail.addLayout(action_row2)
        self.open_data_button = QPushButton("Открыть папку архива ↗")
        self.open_data_button.clicked.connect(self.open_data_folder)
        detail.addWidget(self.open_data_button)

        splitter.addWidget(self.detail_panel)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([720, 410])
        history_layout.addWidget(splitter, 1)
        self.pages.addWidget(self.history_page)

        self.settings_page = self._build_settings_page()
        self.pages.addWidget(self.settings_page)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        outer.addWidget(self.status_label)
        self._set_detail_enabled(False)

    def _add_nav(self, layout, key: str, label: str, callback) -> None:
        button = QPushButton(label)
        button.setObjectName("navButton")
        button.setCheckable(True)
        button.setAutoExclusive(True)
        button.clicked.connect(callback)
        layout.addWidget(button)
        self.nav_buttons[key] = button

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 7, 0, 0)
        layout.setSpacing(14)

        theme_card = QFrame()
        theme_card.setObjectName("settingsCard")
        theme_layout = QVBoxLayout(theme_card)
        theme_layout.setContentsMargins(22, 20, 22, 20)
        title = QLabel("Внешний вид")
        title.setStyleSheet("font-size: 17pt; font-weight: 800;")
        theme_layout.addWidget(title)
        desc = QLabel("Выбери настроение своей библиотеки. Цвета применяются сразу и сохраняются автоматически.")
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        theme_layout.addWidget(desc)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEMES.keys()))
        self.theme_combo.setCurrentText(self.theme_name)
        self.theme_combo.currentTextChanged.connect(self._change_theme)
        theme_layout.addWidget(self.theme_combo)
        layout.addWidget(theme_card)

        privacy_card = QFrame()
        privacy_card.setObjectName("settingsCard")
        privacy_layout = QVBoxLayout(privacy_card)
        privacy_layout.setContentsMargins(22, 20, 22, 20)
        privacy_title = QLabel("Приватность и хранение")
        privacy_title.setStyleSheet("font-size: 17pt; font-weight: 800;")
        privacy_layout.addWidget(privacy_title)
        privacy_text = QLabel(
            "CopySpace хранит историю локально на этом компьютере и не отправляет содержимое в интернет. "
            "Автоматический захват выключен по умолчанию при первом запуске. Фильтр может распознавать "
            "некоторые очевидные пароли и токены, но не обнаруживает все секреты. Не используй приложение "
            "для хранения паролей, банковских данных или приватных ключей."
        )
        privacy_text.setObjectName("muted")
        privacy_text.setWordWrap(True)
        privacy_layout.addWidget(privacy_text)
        folder_label = QLabel(f"Папка архива: {self.store.root}")
        folder_label.setWordWrap(True)
        privacy_layout.addWidget(folder_label)
        clear_button = QPushButton("Очистить всю историю…")
        clear_button.setObjectName("dangerButton")
        clear_button.clicked.connect(self.clear_history)
        privacy_layout.addWidget(clear_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(privacy_card)

        category_card = QFrame()
        category_card.setObjectName("settingsCard")
        cat_layout = QVBoxLayout(category_card)
        cat_layout.setContentsMargins(22, 20, 22, 20)
        cat_title = QLabel("Коллекции")
        cat_title.setStyleSheet("font-size: 17pt; font-weight: 800;")
        cat_layout.addWidget(cat_title)
        cat_desc = QLabel("Создавай собственные коллекции для ссылок, заметок, проектов и других фрагментов. Записи из удалённой коллекции перейдут в «Без категории».")
        cat_desc.setWordWrap(True)
        cat_desc.setObjectName("muted")
        cat_layout.addWidget(cat_desc)
        category_actions = QHBoxLayout()
        add_button = QPushButton("＋ Новая коллекция")
        add_button.setObjectName("primaryButton")
        add_button.clicked.connect(self.add_category)
        remove_button = QPushButton("Удалить коллекцию")
        remove_button.clicked.connect(self.remove_category)
        category_actions.addWidget(add_button)
        category_actions.addWidget(remove_button)
        category_actions.addStretch(1)
        cat_layout.addLayout(category_actions)
        layout.addWidget(category_card)
        layout.addStretch(1)
        return page

    def _apply_theme(self) -> None:
        QApplication.instance().setStyleSheet(build_stylesheet(self.theme_name))

    def _change_theme(self, theme: str) -> None:
        if theme not in THEMES:
            return
        self.theme_name = theme
        self.store.set_setting("theme", theme)
        self._apply_theme()
        self._set_status(f"Тема «{theme}» применена.")

    def _refresh_categories(self) -> None:
        if hasattr(self, "category_filter_combo"):
            self.category_filter_combo.blockSignals(True)
            self.category_filter_combo.clear()
            self.category_filter_combo.addItem("Все коллекции")
            # Keep the default bucket discoverable; items assigned to it must
            # never disappear from the collection selector.
            self.category_filter_combo.addItems(self.store.categories())
            selected = self.category_filter or "Все коллекции"
            index = self.category_filter_combo.findText(selected)
            self.category_filter_combo.setCurrentIndex(index if index >= 0 else 0)
            self.category_filter_combo.blockSignals(False)

        self.detail_category.blockSignals(True)
        current = self.detail_category.currentText()
        self.detail_category.clear()
        self.detail_category.addItems(self.store.categories())
        if current in self.store.categories():
            self.detail_category.setCurrentText(current)
        self.detail_category.blockSignals(False)

    def _collection_filter_changed(self, value: str) -> None:
        if not value:
            return
        self.scope = "all"
        self.category_filter = None if value == "Все коллекции" else value
        self.current_page = "history"
        if self.category_filter:
            self.page_title.setText(self.category_filter)
            self.page_subtitle.setText("Фрагменты, сохранённые в этой коллекции.")
            self._set_nav_checked("")
        elif self.current_page != "settings":
            self.page_title.setText("Моя библиотека")
            self.page_subtitle.setText("Сохранённые фрагменты — в одном спокойном и удобном месте.")
        self._show_history_page()

    def _set_nav_checked(self, key: str) -> None:
        for name, button in self.nav_buttons.items():
            button.setChecked(name == key)

    def _reset_collection_filter(self) -> None:
        self.category_filter_combo.blockSignals(True)
        self.category_filter_combo.setCurrentIndex(0)
        self.category_filter_combo.blockSignals(False)

    def _show_all(self) -> None:
        self.scope, self.category_filter, self.current_page = "all", None, "history"
        self._reset_collection_filter()
        self.page_title.setText("Моя библиотека")
        self.page_subtitle.setText("Сохранённые фрагменты — в одном спокойном и удобном месте.")
        self._set_nav_checked("all")
        self._show_history_page()

    def _show_favorites(self) -> None:
        self.scope, self.category_filter, self.current_page = "favorites", None, "history"
        self._reset_collection_filter()
        self.page_title.setText("Избранное")
        self.page_subtitle.setText("Самое важное — всегда под рукой.")
        self._set_nav_checked("favorites")
        self._show_history_page()

    def _show_text(self) -> None:
        self.scope, self.category_filter, self.current_page = "text", None, "history"
        self._reset_collection_filter()
        self.page_title.setText("Текстовая коллекция")
        self.page_subtitle.setText("Заметки, фразы и фрагменты текста.")
        self._set_nav_checked("text")
        self._show_history_page()

    def _show_links(self) -> None:
        self.scope, self.category_filter, self.current_page = "links", None, "history"
        self._reset_collection_filter()
        self.page_title.setText("Ссылки")
        self.page_subtitle.setText("Адреса сайтов и веб-страницы из буфера обмена.")
        self._set_nav_checked("links")
        self._show_history_page()

    def _show_images(self) -> None:
        self.scope, self.category_filter, self.current_page = "images", None, "history"
        self._reset_collection_filter()
        self.page_title.setText("Изображения")
        self.page_subtitle.setText("Визуальные фрагменты из буфера обмена.")
        self._set_nav_checked("images")
        self._show_history_page()

    def show_category(self, category: str) -> None:
        self.scope, self.category_filter, self.current_page = "all", category, "history"
        self.category_filter_combo.blockSignals(True)
        self.category_filter_combo.setCurrentText(category)
        self.category_filter_combo.blockSignals(False)
        self.page_title.setText(category)
        self.page_subtitle.setText("Твоя персональная коллекция.")
        self._set_nav_checked("")
        self._show_history_page()

    def show_settings(self) -> None:
        self.current_page = "settings"
        self.page_title.setText("Настройки")
        self.page_eyebrow.setText("PERSONAL SPACE  /  PREFERENCES")
        self.page_subtitle.setText("Настрой свою библиотеку и управление захватом.")
        self._set_nav_checked("settings")
        self.pages.setCurrentWidget(self.settings_page)
        self.overview_widget.hide()
        self.search_input.setEnabled(False)
        self.capture_now_button.setEnabled(True)

    def _show_history_page(self) -> None:
        self.page_eyebrow.setText("PERSONAL SPACE  /  CLIPBOARD")
        self.pages.setCurrentWidget(self.history_page)
        self.overview_widget.show()
        self.search_input.setEnabled(True)
        self.refresh_history()

    def refresh_history(self, *_args) -> None:
        if not hasattr(self, "clip_list") or self.current_page == "settings":
            return
        rows = self.store.list_clips(self.scope, self.search_input.text(), self.category_filter)
        selected_id = self.current_clip_id
        self.clip_list.blockSignals(True)
        self.clip_list.clear()
        selected_item = None
        for row in rows:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            item.setSizeHint(QSize(440, 96))
            self.clip_list.addItem(item)
            card = self._make_clip_card(row)
            self.clip_list.setItemWidget(item, card)
            if row["id"] == selected_id:
                selected_item = item
        if selected_item is None and self.clip_list.count():
            selected_item = self.clip_list.item(0)
        if selected_item:
            self.clip_list.setCurrentItem(selected_item)
        self.clip_list.blockSignals(False)
        self._on_selection_changed(self.clip_list.currentItem(), None)
        stats = self.store.stats()
        self.stat_total_value.setText(str(stats["total"]))
        self.stat_text_value.setText(str(stats["text"]))
        self.stat_image_value.setText(str(stats["images"]))
        self.stat_size_value.setText(pretty_size(stats["bytes"]))
        self.stats_label.setText(
            f"{len(rows)} записей в текущем представлении · сортировка: сначала новые"
        )
        self.clip_count_label.setText(str(len(rows)))
        if not rows:
            self.detail_kind.setText("Ничего не найдено")
            self.detail_meta.setText("Скопируй текст или изображение при включённом захвате, либо добавь текущее содержимое буфера вручную.")

    def _make_clip_card(self, row: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("clipCard")
        card.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        card.setMinimumHeight(88)
        outer = QHBoxLayout(card)
        outer.setContentsMargins(11, 10, 12, 10)
        outer.setSpacing(11)

        icon = QLabel("▧" if row["kind"] == "image" else ("↗" if row.get("content_type") == "link" else "T"))
        icon.setObjectName("kindIcon")
        icon.setFixedSize(42, 42)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)

        content = QVBoxLayout()
        content.setContentsMargins(0, 1, 0, 1)
        content.setSpacing(4)
        top = QHBoxLayout()
        content_type = row.get("content_type", "text")
        kind_title = "ИЗОБРАЖЕНИЕ" if row["kind"] == "image" else ("ССЫЛКА" if content_type == "link" else "ТЕКСТОВЫЙ ФРАГМЕНТ")
        kind = QLabel(kind_title)
        kind.setObjectName("clipKind")
        top.addWidget(kind)
        top.addStretch(1)
        flags = []
        if row["pinned"]:
            flags.append("⌖")
        if row["favorite"]:
            flags.append("★")
        if flags:
            marker = QLabel("  ".join(flags))
            marker.setStyleSheet("font-size: 10pt; font-weight: 800;")
            top.addWidget(marker)
        content.addLayout(top)

        preview = QLabel(row["preview"] or "Изображение без текстового описания")
        preview.setObjectName("clipPreview")
        preview.setWordWrap(True)
        preview.setMaximumHeight(36)
        content.addWidget(preview)
        meta = QLabel(f"{row['category']}   /   {pretty_date(row['created_at'])}   /   {pretty_size(row['size_bytes'])}")
        meta.setObjectName("clipMeta")
        content.addWidget(meta)
        outer.addLayout(content, 1)
        return card

    def _on_selection_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        for item, selected in ((previous, False), (current, True)):
            if item is not None:
                card = self.clip_list.itemWidget(item)
                if card is not None:
                    card.setProperty("selected", selected)
                    card.style().unpolish(card)
                    card.style().polish(card)
        if current is None:
            self.current_clip_id = None
            self._set_detail_enabled(False)
            return
        clip_id = int(current.data(Qt.ItemDataRole.UserRole))
        row = self.store.get_clip(clip_id)
        if not row:
            return
        self.current_clip_id = clip_id
        self._set_detail_enabled(True)
        if row["kind"] == "text":
            self.detail_kind.setText("Ссылка" if row.get("content_type") == "link" else "Текстовый фрагмент")
            self.preview_image.hide()
            self.preview_text.show()
            self.preview_text.setPlainText(row["text_content"] or "")
        else:
            self.detail_kind.setText("Изображение")
            self.preview_text.hide()
            self.preview_image.show()
            pixmap = QPixmap(row["image_path"] or "")
            if not pixmap.isNull():
                self.preview_image.setPixmap(pixmap.scaled(330, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                self.preview_image.setText("Изображение недоступно")
        self.detail_meta.setText(
            f"Добавлено: {pretty_date(row['created_at'])}\n"
            f"Размер: {pretty_size(row['size_bytes'])}\n"
            f"Категория: {row['category']}"
        )
        self.detail_category.blockSignals(True)
        self.detail_category.setCurrentText(row["category"])
        self.detail_category.blockSignals(False)
        self.favorite_button.setText("★" if row["favorite"] else "☆")
        self.favorite_button.setToolTip("Убрать из избранного" if row["favorite"] else "Добавить в избранное")
        self.pin_button.setText("Открепить" if row["pinned"] else "Закрепить")

    def _set_detail_enabled(self, enabled: bool) -> None:
        for widget in (
            self.preview_text, self.detail_category, self.copy_button, self.favorite_button,
            self.pin_button, self.delete_button, self.open_data_button,
        ):
            widget.setEnabled(enabled)
        if not enabled:
            self.preview_text.clear()
            self.preview_image.clear()
            self.preview_image.hide()
            self.preview_text.show()
            self.favorite_button.setText("☆")
            self.pin_button.setText("Закрепить")

    def _change_category(self, category: str) -> None:
        if self.current_clip_id is None or not category:
            return
        self.store.update_category(self.current_clip_id, category)
        self.refresh_history()
        self._set_status(f"Категория изменена на «{category}».")

    def copy_selected(self) -> None:
        if self.current_clip_id is None:
            return
        row = self.store.get_clip(self.current_clip_id)
        if not row:
            return
        if row["kind"] == "text":
            self.clipboard.setText(row["text_content"] or "")
        else:
            image = QImage(row["image_path"] or "")
            if image.isNull():
                self._set_status("Не удалось открыть изображение.")
                return
            self.clipboard.setImage(image)
        self._set_status("Скопировано в буфер обмена.")

    def toggle_favorite(self) -> None:
        self._toggle_flag("favorite")

    def toggle_pin(self) -> None:
        self._toggle_flag("pinned")

    def _toggle_flag(self, field: str) -> None:
        if self.current_clip_id is None:
            return
        row = self.store.get_clip(self.current_clip_id)
        if not row:
            return
        self.store.update_flag(self.current_clip_id, field, not bool(row[field]))
        self.refresh_history()

    def delete_selected(self) -> None:
        if self.current_clip_id is None:
            return
        answer = QMessageBox.question(
            self, "Удалить запись", "Удалить выбранную запись из истории CopySpace?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        clip_id = self.current_clip_id
        self.current_clip_id = None
        self.store.delete_clip(clip_id)
        self.refresh_history()
        self._set_status("Запись удалена.")

    def clear_history(self) -> None:
        answer = QMessageBox.warning(
            self, "Очистить историю",
            "Будут удалены все записи CopySpace и сохранённые изображения. Это действие нельзя отменить. Продолжить?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        count = self.store.clear_history()
        self.current_clip_id = None
        self.refresh_history()
        self._set_status(f"История очищена. Удалено записей: {count}.")

    def add_category(self) -> None:
        name, accepted = QInputDialog.getText(self, "Новая категория", "Название категории:")
        if not accepted:
            return
        success, message = self.store.add_category(name)
        if not success:
            QMessageBox.information(self, "Категории", message)
            return
        self._refresh_categories()
        self._set_status(f"Категория «{message}» добавлена.")

    def remove_category(self) -> None:
        candidates = [name for name in self.store.categories() if name != "Без категории"]
        if not candidates:
            QMessageBox.information(self, "Категории", "Нет пользовательских категорий для удаления.")
            return
        name, accepted = QInputDialog.getItem(self, "Удалить категорию", "Выбери категорию:", candidates, 0, False)
        if not accepted:
            return
        success, message = self.store.delete_category(name)
        if success:
            if self.category_filter == name:
                self.category_filter = None
                self.scope = "all"
            self._refresh_categories()
            self.refresh_history()
        QMessageBox.information(self, "Категории", message)

    def toggle_capture(self) -> None:
        self.capture_enabled = not self.capture_enabled
        self.store.set_setting("capture_enabled", "1" if self.capture_enabled else "0")
        self._update_capture_button()
        self._set_status("Захват буфера обмена включён." if self.capture_enabled else "Захват приостановлен.")

    def _update_capture_button(self) -> None:
        if self.capture_enabled:
            self.capture_button.setText("●  Захват включён")
            self.capture_state_label.setText("СОХРАНЕНИЕ В ЭТОМ УСТРОЙСТВЕ")
        else:
            self.capture_button.setText("Ⅱ  Захват на паузе")
            self.capture_state_label.setText("ИСТОРИЯ НЕ ПОПОЛНЯЕТСЯ")
        self.capture_button.setProperty("active", self.capture_enabled)
        self.capture_button.style().unpolish(self.capture_button)
        self.capture_button.style().polish(self.capture_button)

    def _on_clipboard_changed(self) -> None:
        if not self.capture_enabled:
            return
        # Windows applications may publish several clipboard formats in quick
        # succession. A short debounce lets Qt expose the completed payload.
        self._clipboard_capture_timer.start()

    def capture_current_clipboard(self) -> None:
        self._clipboard_capture_timer.stop()
        self._capture_clipboard(manual=True)

    @staticmethod
    def _image_from_mime(mime, clipboard) -> QImage:
        """Extract raster data from standard and app-specific clipboard formats."""
        image = clipboard.image()
        if not image.isNull():
            return image

        image_data = mime.imageData()
        if isinstance(image_data, QImage) and not image_data.isNull():
            return image_data
        if isinstance(image_data, QPixmap) and not image_data.isNull():
            return image_data.toImage()
        if isinstance(image_data, (bytes, bytearray, QByteArray)):
            image = QImage.fromData(bytes(image_data))
            if not image.isNull():
                return image

        # Some Windows applications expose PNG/DIB as a custom MIME format
        # instead of advertising QMimeData.hasImage().
        image_hints = ("image/", "png", "jpeg", "jpg", "bitmap", "dib", "qt-image", "tiff", "webp")
        for mime_format in mime.formats():
            normalized = str(mime_format).lower()
            if not any(hint in normalized for hint in image_hints):
                continue
            raw = mime.data(mime_format)
            if not raw:
                continue
            image = QImage.fromData(bytes(raw))
            if not image.isNull():
                return image
        return QImage()

    def _store_clipboard_image(self, image: QImage) -> dict:
        if image.isNull():
            return {"status": "ignored", "reason": "Не удалось прочитать изображение."}
        if image.width() * image.height() > MAX_IMAGE_PIXELS:
            return {"status": "ignored", "reason": "Изображение слишком большое (лимит 16 мегапикселей)."}
        data = QByteArray()
        buffer = QBuffer(data)
        if not buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not image.save(buffer, "PNG"):
            return {"status": "ignored", "reason": "Не удалось преобразовать изображение в PNG."}
        return self.store.add_image(bytes(data))

    def _capture_clipboard(self, manual: bool) -> None:
        mime = self.clipboard.mimeData()
        try:
            # Direct image payloads take priority over text/HTML alternatives.
            image = self._image_from_mime(mime, self.clipboard)
            if not image.isNull():
                result = self._store_clipboard_image(image)
            elif mime.hasUrls():
                urls = [url for url in mime.urls() if url.isValid()]
                image_file_urls = [
                    url for url in urls
                    if url.isLocalFile()
                    and Path(url.toLocalFile()).suffix.lower() in {
                        ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"
                    }
                ]

                if image_file_urls:
                    results = []
                    for url in image_file_urls:
                        file_path = Path(url.toLocalFile())
                        imported_image = QImage(str(file_path))
                        if imported_image.isNull():
                            results.append({"status": "ignored", "reason": f"Не удалось открыть изображение: {file_path.name}"})
                        else:
                            results.append(self._store_clipboard_image(imported_image))
                    saved_count = sum(item.get("status") == "saved" for item in results)
                    duplicate_count = sum(item.get("status") == "duplicate" for item in results)
                    if saved_count or duplicate_count:
                        self.refresh_history()
                        self._set_status(f"Добавлено изображений: {saved_count}" + (f", уже были в истории: {duplicate_count}." if duplicate_count else "."))
                        return
                    reasons = [str(item.get("reason")) for item in results if item.get("reason")]
                    self._set_status(reasons[0] if reasons else "Не удалось импортировать изображения.")
                    return

                # A file:// URL is a local file, not a web link. Keep other
                # copied file paths as plain text instead of putting them in Links.
                web_urls = [url.toString() for url in urls if not url.isLocalFile()]
                if web_urls:
                    link_text = "\n".join(web_urls)
                    content_type, suggested_category = classify_clipboard_text(link_text)
                    result = self.store.add_text(
                        link_text, category=suggested_category, content_type=content_type
                    )
                else:
                    local_paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
                    if not local_paths:
                        self._set_status("В буфере нет корректной ссылки или файла.")
                        return
                    result = self.store.add_text("\n".join(local_paths))
            elif mime.hasText():
                copied_text = self.clipboard.text()
                content_type, suggested_category = classify_clipboard_text(copied_text)
                result = self.store.add_text(
                    copied_text, category=suggested_category, content_type=content_type
                )
            else:
                self._set_status("В буфере нет текста или изображения.")
                return
        except Exception as exc:
            self._set_status(f"Ошибка сохранения: {exc}")
            return

        status = result.get("status")
        if status in {"saved", "duplicate"}:
            self.refresh_history()
        if status == "saved":
            self._set_status("Добавлено в историю." if manual else "Новый элемент сохранён.")
        elif status == "blocked":
            self._set_status(str(result.get("reason", "Похоже на чувствительные данные — не сохранено.")))
        elif status == "ignored":
            self._set_status(str(result.get("reason", "Элемент не добавлен.")))
        elif status == "duplicate":
            self._set_status("Этот элемент уже есть в истории.")

    def open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root)))

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        try:
            self.store.close()
        finally:
            event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("CopySpace")
    window = CopySpaceWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
