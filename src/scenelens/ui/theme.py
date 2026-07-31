from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication

from scenelens.storage.app_settings import AppSettings


@dataclass(frozen=True)
class ThemeTokens:
    window: str
    surface: str
    surface_alt: str
    surface_raised: str
    input: str
    border: str
    border_strong: str
    text: str
    muted: str
    subtle: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str
    accent_text: str
    selection_text: str
    warning: str
    danger: str
    success: str


_ACCENTS = {
    "violet": {
        "dark": ("#8B7CF6", "#9D91FA", "#7162DF", "#332E5C"),
        "light": ("#6758D8", "#584AC3", "#493BAB", "#E9E6FB"),
    },
    "blue": {
        "dark": ("#65A8FF", "#7BB5FF", "#4D8EE2", "#243E5F"),
        "light": ("#2F78D4", "#2468BC", "#1D58A2", "#E2EFFD"),
    },
    "teal": {
        "dark": ("#48C7B5", "#61D2C1", "#34A997", "#214C48"),
        "light": ("#168E80", "#117B70", "#0D695F", "#DDF5F1"),
    },
    "orange": {
        "dark": ("#F0A45D", "#F5B271", "#D78942", "#593D28"),
        "light": ("#C56A20", "#AD5B19", "#934C14", "#FBEBDD"),
    },
}


def resolved_theme_mode(app: QApplication, requested: str) -> str:
    if requested in {"light", "dark"}:
        return requested
    scheme = app.styleHints().colorScheme()
    return (
        "dark"
        if scheme == Qt.ColorScheme.Dark
        else "light"
    )


def theme_tokens(mode: str, accent_id: str) -> ThemeTokens:
    accent, hover, pressed, soft = _ACCENTS[accent_id][mode]
    if mode == "dark":
        return ThemeTokens(
            window="#111318",
            surface="#191C22",
            surface_alt="#15181E",
            surface_raised="#22262E",
            input="#14171D",
            border="#313640",
            border_strong="#454C59",
            text="#F2F4F8",
            muted="#A9B0BC",
            subtle="#737B88",
            accent=accent,
            accent_hover=hover,
            accent_pressed=pressed,
            accent_soft=soft,
            accent_text="#101218",
            selection_text="#FFFFFF",
            warning="#F1B75B",
            danger="#FF7B83",
            success="#62D49F",
        )
    return ThemeTokens(
        window="#F4F5F8",
        surface="#FFFFFF",
        surface_alt="#EEF0F5",
        surface_raised="#F9FAFC",
        input="#FFFFFF",
        border="#D8DCE5",
        border_strong="#BFC5D1",
        text="#20242C",
        muted="#626A78",
        subtle="#858D9A",
        accent=accent,
        accent_hover=hover,
        accent_pressed=pressed,
        accent_soft=soft,
        accent_text="#FFFFFF",
        selection_text="#FFFFFF",
        warning="#9A5C12",
        danger="#C33E49",
        success="#177A51",
    )


def build_palette(tokens: ThemeTokens) -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(tokens.window))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(tokens.text))
    palette.setColor(QPalette.ColorRole.Base, QColor(tokens.input))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens.surface_alt))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(tokens.surface_raised))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(tokens.text))
    palette.setColor(QPalette.ColorRole.Text, QColor(tokens.text))
    palette.setColor(QPalette.ColorRole.Button, QColor(tokens.surface_raised))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(tokens.text))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(tokens.danger))
    palette.setColor(QPalette.ColorRole.Link, QColor(tokens.accent))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens.accent))
    palette.setColor(
        QPalette.ColorRole.HighlightedText,
        QColor(tokens.selection_text),
    )
    palette.setColor(
        QPalette.ColorRole.PlaceholderText,
        QColor(tokens.subtle),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(tokens.subtle),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(tokens.subtle),
    )
    return palette


def _density_values(mode: str) -> tuple[int, int, int, int]:
    return {
        "compact": (4, 7, 5, 28),
        "comfortable": (6, 10, 7, 32),
        "spacious": (8, 13, 9, 36),
    }[mode]


def build_stylesheet(tokens: ThemeTokens, settings: AppSettings) -> str:
    vertical, horizontal, tab_vertical, control_height = _density_values(
        settings.density
    )
    return f"""
QWidget {{
    color: {tokens.text};
    font-size: {settings.font_size}pt;
}}
QMainWindow, QDialog {{
    background-color: {tokens.window};
}}
QLabel {{
    background: transparent;
}}
QMenuBar {{
    background-color: {tokens.surface};
    border-bottom: 1px solid {tokens.border};
    padding: 3px 8px;
}}
QMenuBar::item {{
    background: transparent;
    border-radius: 5px;
    padding: 5px 9px;
}}
QMenuBar::item:selected {{
    background: {tokens.surface_raised};
}}
QMenu {{
    background: {tokens.surface};
    border: 1px solid {tokens.border};
    border-radius: 7px;
    padding: 5px;
}}
QMenu::item {{
    border-radius: 5px;
    padding: 7px 28px 7px 10px;
}}
QMenu::item:selected {{
    background: {tokens.accent_soft};
    color: {tokens.text};
}}
QToolBar {{
    background: {tokens.surface};
    border: none;
    border-bottom: 1px solid {tokens.border};
    spacing: 5px;
    padding: 6px 8px;
}}
QToolBar::separator {{
    background: {tokens.border};
    width: 1px;
    margin: 5px 7px;
}}
QStatusBar {{
    background: {tokens.surface};
    border-top: 1px solid {tokens.border};
    color: {tokens.muted};
}}
QDockWidget {{
    color: {tokens.text};
    font-weight: 600;
}}
QDockWidget::title {{
    background: {tokens.surface};
    border-bottom: 1px solid {tokens.border};
    padding: 8px 10px;
    text-align: left;
}}
QDockWidget > QWidget {{
    background: {tokens.surface_alt};
}}
QGroupBox {{
    background: {tokens.surface};
    border: 1px solid {tokens.border};
    border-radius: 9px;
    margin-top: 13px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 5px;
    color: {tokens.muted};
}}
QPushButton, QToolButton {{
    background: {tokens.surface_raised};
    border: 1px solid {tokens.border_strong};
    border-radius: 7px;
    padding: {vertical}px {horizontal}px;
    min-height: {control_height - 2}px;
}}
QPushButton:hover, QToolButton:hover {{
    border-color: {tokens.accent};
    background: {tokens.accent_soft};
}}
QPushButton:pressed, QToolButton:pressed {{
    background: {tokens.surface_alt};
    border-color: {tokens.accent_pressed};
}}
QPushButton:disabled, QToolButton:disabled {{
    color: {tokens.subtle};
    border-color: {tokens.border};
    background: {tokens.surface_alt};
}}
QPushButton[primary="true"], QToolButton[primary="true"] {{
    color: {tokens.accent_text};
    background: {tokens.accent};
    border-color: {tokens.accent};
    font-weight: 700;
}}
QPushButton[primary="true"]:hover, QToolButton[primary="true"]:hover {{
    background: {tokens.accent_hover};
    border-color: {tokens.accent_hover};
}}
QPushButton[primary="true"]:disabled, QToolButton[primary="true"]:disabled {{
    color: {tokens.subtle};
    background: {tokens.surface_alt};
    border-color: {tokens.border};
}}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox,
QDateEdit, QTimeEdit, QComboBox {{
    background: {tokens.input};
    color: {tokens.text};
    border: 1px solid {tokens.border_strong};
    border-radius: 7px;
    padding: {vertical}px {horizontal}px;
    selection-background-color: {tokens.accent};
    selection-color: {tokens.selection_text};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {tokens.accent};
}}
QComboBox::drop-down {{
    border: none;
    width: 26px;
}}
QComboBox QAbstractItemView {{
    background: {tokens.surface};
    border: 1px solid {tokens.border};
    selection-background-color: {tokens.accent_soft};
    selection-color: {tokens.text};
    outline: none;
}}
QAbstractItemView, QTableView, QTreeView, QListView {{
    background: {tokens.surface};
    alternate-background-color: {tokens.surface_alt};
    color: {tokens.text};
    border: 1px solid {tokens.border};
    border-radius: 7px;
    outline: none;
    selection-background-color: {tokens.accent_soft};
    selection-color: {tokens.text};
}}
QAbstractItemView::item {{
    padding: {vertical}px 6px;
    border: none;
}}
QAbstractItemView::item:hover {{
    background: {tokens.surface_raised};
}}
QHeaderView::section {{
    background: {tokens.surface_alt};
    color: {tokens.muted};
    border: none;
    border-right: 1px solid {tokens.border};
    border-bottom: 1px solid {tokens.border};
    padding: {vertical + 1}px 7px;
    font-weight: 600;
}}
QTabWidget::pane {{
    background: {tokens.surface};
    border: 1px solid {tokens.border};
    border-radius: 8px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {tokens.muted};
    border: none;
    border-bottom: 2px solid transparent;
    padding: {tab_vertical}px 12px;
}}
QTabBar::tab:hover {{
    color: {tokens.text};
    background: {tokens.surface_raised};
}}
QTabBar::tab:selected {{
    color: {tokens.text};
    border-bottom-color: {tokens.accent};
    font-weight: 700;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {tokens.border_strong};
    min-height: 32px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background: {tokens.muted};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {tokens.border_strong};
    min-width: 32px;
    border-radius: 5px;
}}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
    border: none;
}}
QSplitter::handle {{
    background: {tokens.border};
}}
QSplitter::handle:hover {{
    background: {tokens.accent};
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {tokens.border_strong};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {tokens.accent};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 16px;
    margin: -6px 0;
    border: 2px solid {tokens.surface};
    border-radius: 8px;
    background: {tokens.accent};
}}
QProgressBar {{
    background: {tokens.surface_alt};
    border: 1px solid {tokens.border};
    border-radius: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {tokens.accent};
    border-radius: 5px;
}}
QCheckBox, QRadioButton {{
    spacing: 7px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
}}
QToolTip {{
    color: {tokens.text};
    background: {tokens.surface_raised};
    border: 1px solid {tokens.border_strong};
    padding: 5px;
}}
QLabel[role="muted"] {{
    color: {tokens.muted};
}}
QLabel[role="subtle"] {{
    color: {tokens.subtle};
}}
QLabel[tone="warning"] {{
    color: {tokens.warning};
}}
QLabel[tone="danger"] {{
    color: {tokens.danger};
}}
QLabel[tone="success"] {{
    color: {tokens.success};
}}
QLabel[role="paneTitle"] {{
    background: {tokens.surface};
    border-bottom: 1px solid {tokens.border};
    padding: 8px 10px;
    font-weight: 700;
}}
QLabel#analysisThumbnail {{
    background: #111318;
    color: #8E96A3;
    border: 1px solid {tokens.border};
    border-radius: 7px;
}}
QFrame#workspaceCard {{
    background: {tokens.surface};
    border: 1px solid {tokens.border};
    border-radius: 14px;
}}
QFrame#workspaceCard:hover {{
    border-color: {tokens.accent};
    background: {tokens.surface_raised};
}}
QFrame#heroPanel {{
    background: {tokens.surface};
    border: 1px solid {tokens.border};
    border-radius: 16px;
}}
QFrame#settingsPreviewCard {{
    background: {tokens.surface_alt};
    border: 1px solid {tokens.border};
    border-radius: 10px;
}}
QLabel#brandMark {{
    color: {tokens.accent_text};
    background: {tokens.accent};
    border-radius: 10px;
    font-weight: 800;
}}
QLabel#brandTitle {{
    font-size: {settings.font_size + 13}pt;
    font-weight: 800;
}}
QLabel#heroTitle {{
    font-size: {settings.font_size + 10}pt;
    font-weight: 800;
}}
QLabel#cardIndex {{
    color: {tokens.accent};
    font-weight: 800;
}}
QLabel#cardTitle {{
    font-size: {settings.font_size + 5}pt;
    font-weight: 750;
}}
"""


def apply_appearance(app: QApplication, settings: AppSettings) -> str:
    mode = resolved_theme_mode(app, settings.theme_mode)
    tokens = theme_tokens(mode, settings.accent)
    app.setPalette(build_palette(tokens))
    app.setFont(QFont("Microsoft YaHei UI", settings.font_size))
    app.setStyleSheet(build_stylesheet(tokens, settings))
    app.setProperty("gatalkThemeMode", mode)
    app.setProperty("gatalkAccent", settings.accent)
    return mode


def create_brand_icon(size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor("#9B8AFB"))
    gradient.setColorAt(1.0, QColor("#4D8EE2"))
    painter.setBrush(gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    inset = max(2, size // 16)
    painter.drawRoundedRect(
        inset,
        inset,
        size - inset * 2,
        size - inset * 2,
        size * 0.22,
        size * 0.22,
    )
    font = QFont("Segoe UI", max(9, int(size * 0.29)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QPen(QColor("#FFFFFF")))
    painter.drawText(
        pixmap.rect(),
        Qt.AlignmentFlag.AlignCenter,
        "GA",
    )
    painter.end()
    return QIcon(pixmap)
