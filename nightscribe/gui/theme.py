############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - global dark theme module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# Single source of truth for the application's visual identity (ADR-026).
# Before this file, the dark look was hand-rolled widget by widget: the
# Tonight cards were dark while tabs, menus, tables and dialogs kept the
# platform (light) style. Now the whole app speaks the same language.
#
# The palette and the stylesheet only style *chrome* (containers, widgets);
# content colors (per-kind accents, buttons like Start/Continue) keep their
# own inline styles, which override the global ones — that stays on purpose.


# Per-kind accent colors, shared by cards, icons and table tints.
# Bright enough to read on a #12141f surface (readable-contrast rule).
KIND_COLORS = {
    "sn": "#e05555",
    "neo": "#5588dd",
    "comet": "#55bb66",
    "pccp": "#dd9944",
    "transit": "#aa77cc",
    "alert": "#ddaa44",
}

# Short chips used next to object names ("NEO", "SN", ...).
KIND_LABELS = {
    "neo": "NEO", "sn": "SN", "comet": "CMT",
    "pccp": "PCCP", "transit": "TRN", "alert": "ALT",
}

# Core palette — one warm-black blue family, no pure black.
C_BG = "#0f121c"        # windows
C_BASE = "#12141f"      # inputs, tables, cards
C_PANEL = "#171a26"     # buttons, headers, raised panels
C_LINE = "#232736"      # borders, gridlines, splitters
C_SEL = "#2f4d80"       # selection highlight (accent-tinted, white text)
C_TEXT = "#e8eaf2"      # main text
C_TEXT_DIM = "#8a90a6"  # secondary text (headers, context lines)
C_ACCENT = "#6ab0ff"    # links, focus, interactive accents
C_WARN = "#cc8844"      # warnings (moon, mag-limit)
C_GOOD = "#66cc99"      # "up now" state
C_OK = "#99bbdd"        # informative badges (rise times)


def _palette():
    # @return: a QPalette for the Fusion style in our dark family.
    from PySide6.QtGui import QColor, QPalette
    c = _c(C_BG)
    p = QPalette()
    p.setColor(QPalette.Window, c)
    p.setColor(QPalette.WindowText, _c(C_TEXT))
    p.setColor(QPalette.Base, _c(C_BASE))
    p.setColor(QPalette.AlternateBase, _c(C_PANEL))
    p.setColor(QPalette.Text, _c(C_TEXT))
    p.setColor(QPalette.Button, _c(C_PANEL))
    p.setColor(QPalette.ButtonText, _c(C_TEXT))
    p.setColor(QPalette.BrightText, QColor("#ffffff"))
    p.setColor(QPalette.Highlight, _c(C_SEL))
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ToolTipBase, _c(C_PANEL))
    p.setColor(QPalette.ToolTipText, _c(C_TEXT))
    p.setColor(QPalette.Link, _c(C_ACCENT))
    p.setColor(QPalette.Light, _c(C_LINE))
    p.setColor(QPalette.Midlight, _c(C_LINE))
    p.setColor(QPalette.Mid, _c("#1c202e"))
    p.setColor(QPalette.Dark, _c("#0a0c12"))
    p.setColor(QPalette.Shadow, _c("#07080d"))
    p.setColor(QPalette.PlaceholderText, _c(C_TEXT_DIM))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, _c(C_TEXT_DIM))
    return p


def _c(hex_):
    # Small helper so the palette code stays a flat list.
    from PySide6.QtGui import QColor
    return QColor(hex_)


def apply_theme(app):
    # Applies the NightScribe dark theme to a live QApplication:
    # Fusion base style, dark palette, and the global stylesheet.
    # Call once, right after the QApplication is created (app.py).
    # @args: app - the QApplication
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setStyleSheet(_QSS)


_QSS = f"""
/* ---- base ----------------------------------------------------------- */
* {{ font-size: 13px; }}

QMainWindow, QDialog {{ background: {C_BG}; color: {C_TEXT}; }}
QWidget {{ color: {C_TEXT}; }}

/* ---- buttons --------------------------------------------------------- */
QPushButton {{
    background: {C_PANEL}; color: {C_TEXT}; border: none;
    border-radius: 4px; padding: 6px 16px;
}}
QPushButton:hover {{ background: #212739; }}
QPushButton:pressed {{ background: {C_SEL}; }}
QPushButton:disabled {{ color: {C_TEXT_DIM}; background: #141824; }}
QPushButton:flat {{ background: transparent; }}
QPushButton:flat:hover {{ background: rgba(255,255,255,0.06); }}
QToolButton {{
    background: transparent; color: {C_TEXT}; border: none;
    padding: 4px; border-radius: 4px;
}}
QToolButton:hover {{ background: rgba(255,255,255,0.08); }}

/* ---- menus ------------------------------------------------------------ */
QMenuBar {{ background: {C_BASE}; color: {C_TEXT}; }}
QMenuBar::item {{ background: transparent; padding: 6px 12px; }}
QMenuBar::item:selected {{ background: {C_SEL}; border-radius: 3px; }}
QMenu {{
    background: {C_PANEL}; color: {C_TEXT};
    border: 1px solid {C_LINE}; padding: 4px 0;
}}
QMenu::item {{ padding: 6px 28px 6px 24px; }}
QMenu::item:selected {{ background: {C_SEL}; }}
QMenu::separator {{ height: 1px; background: {C_LINE}; margin: 4px 10px; }}

/* ---- tabs --------------------------------------------------------------- */
QTabWidget::pane {{ border: none; background: {C_BG}; top: -1px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {C_TEXT_DIM};
    padding: 9px 20px; border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {C_TEXT}; border-bottom: 2px solid {C_ACCENT};
    font-weight: bold;
}}
QTabBar::tab:hover {{ color: {C_TEXT}; }}

/* ---- inputs -------------------------------------------------------------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QTextBrowser {{
    background: {C_BASE}; color: {C_TEXT};
    border: 1px solid {C_LINE}; border-radius: 4px; padding: 4px 8px;
    selection-background-color: {C_SEL};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {C_ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {C_PANEL}; color: {C_TEXT};
    border: 1px solid {C_LINE}; selection-background-color: {C_SEL};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: {C_PANEL}; border: none;
}}
QCheckBox, QRadioButton {{ spacing: 8px; color: {C_TEXT}; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
}}
QProgressBar {{
    background: {C_BASE}; color: {C_TEXT};
    border: 1px solid {C_LINE}; border-radius: 4px;
    text-align: center;
}}
QProgressBar::chunk {{ background: {C_ACCENT}; }}

/* ---- tables and lists --------------------------------------------------- */
QTableWidget, QTableView, QTreeView, QListView, QListView::item {{
    background: {C_BASE}; color: {C_TEXT};
    alternate-background-color: #141824;
    gridline-color: {C_LINE};
}}
QTableWidget::item:selected, QTreeView::item:selected, QListView::item:selected {{
    background: {C_SEL}; color: #ffffff;
}}
QHeaderView::section {{
    background: {C_PANEL}; color: {C_TEXT_DIM};
    border: none; border-bottom: 1px solid {C_LINE};
    padding: 6px 8px;
}}
QTableCornerButton::section {{ background: {C_PANEL}; border: none; }}
QTableWidget {{ border: 1px solid {C_LINE}; border-radius: 6px; }}

/* ---- groups, toolbars, status ------------------------------------------------ */
QGroupBox {{
    border: 1px solid {C_LINE}; border-radius: 6px;
    margin-top: 12px; padding-top: 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 10px; padding: 0 4px;
    color: {C_TEXT_DIM};
}}
QToolBar {{ background: {C_PANEL}; border: none; spacing: 4px; }}
QStatusBar {{
    background: {C_BASE}; color: {C_TEXT_DIM}; border-top: 1px solid {C_LINE};
}}
QStatusBar QLabel {{ background: transparent; color: {C_TEXT_DIM}; }}
QSplitter::handle {{ background: {C_LINE}; width: 1px; }}

/* ---- tooltips ----------------------------------------------------------- */
QToolTip {{
    background: {C_PANEL}; color: {C_TEXT};
    border: 1px solid {C_LINE}; padding: 6px 10px;
}}

/* ---- scrollbars ---------------------------------------------------------- */
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {C_LINE}; min-height: 30px; border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{ background: #333d55; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {C_LINE}; min-width: 30px; border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{ background: #333d55; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ---- misc ----------------------------------------------------------------- */
QFrame {{ color: {C_TEXT}; }}
QLabel {{ background: transparent; color: {C_TEXT}; }}
QLabel:disabled {{ color: {C_TEXT_DIM}; }}
"""
