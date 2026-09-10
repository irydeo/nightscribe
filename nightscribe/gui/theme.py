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


from pathlib import Path

# Bundled vector assets live next to moon_disk.png (same loading pattern as
# moon_icon.py): the QSS references check.svg by URL to paint the tick inside
# a checked indicator — files, not compiled qrc resources.
_ASSETS = Path(__file__).resolve().parent.parent / "assets"
CHECK_SVG = str(_ASSETS / "check.svg")


# Per-kind accent colors, shared by cards, icons and table names.
# Six well-separated hues on the wheel (0/28/140/185/218/268°),
# none in the amber band (40-65°), all saturated, mid-value.
KIND_COLORS = {
    "sn":      "#e5484d",   # 0°   red
    "alert":   "#f76808",   # 24°  orange (NOT yellow)
    "comet":   "#46a758",   # 140° green
    "pccp":    "#39c5cf",   # 185° cyan (clearly away from green AND blue)
    "neo":     "#4484ef",   # 216° blue
    "transit": "#a06ee0",   # 268° purple
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
C_WARN = "#f76808"      # warnings (moon, mag-limit) — orange, same as alert
C_GOOD = "#46a758"      # "up now" state — matches the comet green
C_OK   = "#4484ef"      # informative (rise times, windows) — matches neo blue
C_EDGE = "#3a4156"      # borders of interactive containers (checkbox frame,
                        # input fields, list/table boxes, popups) — reads as
                        # "this is clickable" against C_BASE/C_PANEL (>=1.5:1)
C_HOVER = "#212739"     # push-button hover fill (was a hardcoded literal)
C_DIM_FILL = "#141824"  # disabled button fills, alternate table rows
# Pills are solid badges (no alpha): the hue *is* the surface, and the label
# is picked per hue for contrast (near-black on bright hues, white on dark).
# Transparency over the dark card was exactly what made every chip read dim
# and washed out, no matter how saturated the hue.
C_CHIP_TEXT_DARK = "#11141d"   # the label color on bright surfaces


def _lum(hex_):
    # @args: a #rrggbb hex string
    # @return: its relative luminance (0..1), the WCAG definition.
    h = hex_.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
         for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def chip_text_for(surface):
    # @args: a hex surface color (what goes behind the pill)
    # @return: the light or the dark app text — whichever contrasts more.
    s = _lum(surface)
    light = (1.005) / (s + 0.05)
    dark = (s + 0.05) / (_lum(C_CHIP_TEXT_DARK) + 0.05)
    return C_CHIP_TEXT_DARK if dark > light else C_TEXT


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


def chip_style(color, font_size=11):
    # @args: a hex surface color (e.g. KIND_COLORS['comet']), px font size
    # @return: a stylesheet string for a small pill label.
    #   A solid badge in that hue with the more legible text color on top:
    #   the hue identifies the kind, the label is never washed out. Solid
    #   (no alpha) on purpose — any hue over the dark card at a fraction
    #   reads dim and muddy no matter how saturated it is. Both the Tonight
    #   rows and the project overview build their mag / rate / window /
    #   moon chips through here so they match.
    return (f"color: {chip_text_for(color)}; "
            f"font-size: {font_size}px; font-weight: bold;"
            f" padding: 2px 8px; border-radius: 8px;"
            f" background: {color};")


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
QPushButton:hover {{ background: {C_HOVER}; }}
QPushButton:pressed {{ background: {C_SEL}; }}
QPushButton:disabled {{ color: {C_TEXT_DIM}; background: {C_DIM_FILL}; }}
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
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QTextBrowser,
QPlainTextEdit {{
    background: {C_BASE}; color: {C_TEXT};
    border: 1px solid {C_EDGE}; border-radius: 4px; padding: 4px 8px;
    selection-background-color: {C_SEL};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {C_ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {C_PANEL}; color: {C_TEXT};
    border: 1px solid {C_EDGE}; selection-background-color: {C_SEL};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: {C_PANEL}; border: none;
}}
QCheckBox, QRadioButton {{ spacing: 8px; color: {C_TEXT}; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 17px; height: 17px;
    border: 1px solid {C_EDGE}; border-radius: 4px;
    background: #0a0d16;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border: 1px solid {C_ACCENT};
}}
QCheckBox::indicator:pressed, QRadioButton::indicator:pressed {{
    background: {C_SEL};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    border: 1px solid {C_LINE}; background: {C_DIM_FILL};
}}
QCheckBox::indicator:checked {{
    background: {C_ACCENT}; border: 1px solid {C_ACCENT};
    image: url("{CHECK_SVG}");
}}
QRadioButton::indicator {{ border-radius: 9px; }}
QRadioButton::indicator:checked {{
    /* accent dot with a dark ring: the 4px border hollows the centre */
    background: {C_ACCENT}; border: 4px solid #0a0d16;
}}
QProgressBar {{
    background: {C_BASE}; color: {C_TEXT};
    border: 1px solid {C_LINE}; border-radius: 4px;
    text-align: center;
}}
QProgressBar::chunk {{ background: {C_ACCENT}; }}

/* ---- tables and lists --------------------------------------------------- */
/* Views are explicit containers: a visible edge (C_EDGE) keeps a list from
   melting into the window, and hover lets you follow the item under the
   mouse. The selected accent stays as the one "active" surface colour. */
QTableWidget, QTableView, QTreeView, QListView, QListWidget {{
    background: {C_BASE}; color: {C_TEXT};
    alternate-background-color: {C_DIM_FILL};
    gridline-color: {C_LINE};
    border: 1px solid {C_EDGE}; border-radius: 6px;
}}
QListView::item, QListWidget::item {{ padding: 5px 8px; }}
QTableWidget::item:hover, QTreeView::item:hover,
QListView::item:hover, QListWidget::item:hover {{
    background: {C_PANEL};
}}
QTableWidget::item:selected, QTreeView::item:selected,
QListView::item:selected, QListWidget::item:selected {{
    background: {C_SEL}; color: #ffffff;
}}
QHeaderView::section {{
    background: {C_PANEL}; color: {C_TEXT_DIM};
    border: none; border-bottom: 1px solid {C_LINE};
    border-right: 1px solid {C_EDGE};
    padding: 6px 8px;
}}
QTableCornerButton::section {{ background: {C_PANEL}; border: none; }}

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
/* calm text: bright white (#e8eaf2) reads as a glare box on the dark app */
QToolTip {{
    background: {C_PANEL}; color: {C_TEXT_DIM};
    border: 1px solid {C_LINE}; border-radius: 4px; padding: 7px 11px;
}}

/* ---- scrollbars ---------------------------------------------------------- */
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {C_LINE}; min-height: 30px; border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{ background: {C_EDGE}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {C_LINE}; min-width: 30px; border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{ background: {C_EDGE}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ---- misc ----------------------------------------------------------------- */
QFrame {{ color: {C_TEXT}; }}
QLabel {{ background: transparent; color: {C_TEXT}; }}
QLabel:disabled {{ color: {C_TEXT_DIM}; }}
"""
