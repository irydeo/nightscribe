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
# POSIX form on purpose: Qt's QSS parser reads backslashes as escape
# characters, so a native Windows path ("C:\...") corrupts the url() and the
# tick falls back to a black native check on the dark box. "C:/..." works
# everywhere (identical to str(path) on Linux).
CHECK_SVG = (_ASSETS / "check.svg").as_posix()
# Same POSIX-path reasoning as CHECK_SVG: the QSS references these in the
# spinbox / combo arrows (a styled widget's arrows are NOT painted by the
# style unless the sheet gives them an image).
ARROW_UP_SVG = (_ASSETS / "arrow_up.svg").as_posix()
ARROW_DOWN_SVG = (_ASSETS / "arrow_down.svg").as_posix()


def asset(name):
    # @args: name - a file name inside the bundled assets folder (SVG, PNG)
    # @return: its Path; the caller wraps it in a QIcon or a QSS url().
    #          Do not assume it exists: check with path.exists() first.
    return _ASSETS / name


def app_logo(size=64):
    # The application logo (the quill + four-point star tile) as a scaled
    # QPixmap for the Welcome hero and the navigation bar. Returns a null
    # QPixmap when the asset is missing, so callers can just skip it.
    # @args: size - the square edge in px
    # @return: a QPixmap (may be null)
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    png = _ASSETS / "appicon-256.png"
    if not png.exists():
        return QPixmap()
    pm = QPixmap(str(png))
    if pm.isNull():
        return pm
    return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


# Per-kind accent colors, shared by cards, icons and table names.
# Eight well-separated hues on the wheel (0/24/100/140/185/216/268/320°),
# none in the amber band (40-65°), all saturated, mid-value.
KIND_COLORS = {
    "sn":      "#e5484d",   # 0°   red
    "alert":   "#f76808",   # 24°  orange (NOT yellow)
    "variable": "#65cf30",  # 100° yellow-green (the last free arc)
    "comet":   "#46a758",   # 140° green
    "pccp":    "#39c5cf",   # 185° cyan (clearly away from green AND blue)
    "neo":     "#4484ef",   # 216° blue
    "transit": "#a06ee0",   # 268° purple
    "hads":    "#e0549e",   # 320° magenta (largest free arc)
}

# Short chips used next to object names ("NEO", "SN", ...).
KIND_LABELS = {
    "neo": "NEO", "sn": "SN", "comet": "CMT",
    "pccp": "PCCP", "transit": "TRN", "alert": "ALT", "hads": "HADS",
    "variable": "VAR",
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
C_ROW_HOVER = "#1a1f30" # list-row hover fill (was a literal in every row widget)
# Urgent "event" red — the same hue as the SN red: one wheel, one meaning.
# A detector event in a campaign, an "event" urgency in the dashboard.
C_EVENT = "#e5484d"
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


def hero_button_style(hue):
    # The ONE action of a panel (ADR-038), painted in the object's own hue.
    # @args: hue - the project's kind hue (a KIND_COLORS value), or the app
    #        accent when there is no project
    # @return: a stylesheet for that button, applied to the INSTANCE (the
    #          hue changes with the project, so it cannot live in the
    #          global sheet).
    #
    # Three decisions, each with its measurement:
    #
    # * The gradient goes from a LIGHTER tone at the top down to the hue.
    #   The chip grammar picks the text by contrast (chip_text_for) and every
    #   kind hue takes the DARK text: darkening the fill downwards would eat
    #   the contrast (measured: the SN red at -20% drops from 4.7:1 to
    #   3.2:1), while lifting the top stop raises it (5.1:1 for the same red).
    # * The border stays 2 px in every state and only changes COLOUR on
    #   focus: a border that grows would move the button under the cursor.
    # * Solid fills, never an alpha wash: over the dark panel a translucent
    #   hue reads muddy (the lesson the chips already carry).
    #
    # The horizontal padding is 16 px, not 20, and the caller draws the glyph
    # at 18 px: the panel's column is 380 px wide and the longest label
    # ("Construir la secuencia (comparsas)…") measured 363 px with 20/22, one
    # pixel MORE than the 362 it has. With 16/18 it is 351 px, so the label
    # fits in both languages with room to spare.
    text = chip_text_for(hue)
    top = composite(hue, "f0", over="#ffffff")      # +6% toward white
    hover = composite(hue, "e6", over="#ffffff")    # +10%
    pressed = composite(hue, "e6", over="#000000")  # -10%
    rim = composite(hue, "8c", over="#000000")      # 55% of the hue
    return (
        f"QPushButton {{"
        f" background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f" stop:0 {top}, stop:1 {hue});"
        f" color: {text}; border: 2px solid {rim}; border-radius: 12px;"
        f" padding: 12px 16px; font-size: 16px; font-weight: 700; }}"
        f"QPushButton:hover {{ background: {hover}; }}"
        f"QPushButton:pressed {{ background: {pressed};"
        f" padding-top: 13px; }}"
        f"QPushButton:focus {{ border: 2px solid #ffffff; }}"
        f"QPushButton:disabled {{ background: {C_DIM_FILL};"
        f" color: {C_TEXT_DIM}; border: 2px solid {C_LINE}; }}")


def hero_cancel_style():
    # What the hero button becomes WHILE it runs: the same size and weight,
    # but quiet and outlined, because it is no longer the action of the panel
    # (the run is). The label changes to Cancel in the same move.
    # @return: a stylesheet for that button
    return (f"QPushButton {{ background: transparent; color: {C_TEXT};"
            f" border: 2px solid {C_LINE}; border-radius: 12px;"
            f" padding: 12px 16px; font-size: 16px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {C_HOVER};"
            f" border-color: {C_WARN}; color: {C_WARN}; }}")


def block_header_style(hue=None):
    # The header of a collapsible CARD: transparent (the card paints the
    # surface and its border) with the title in the card's accent, which is
    # the same grammar the object card's sections use (theme.section_card_style
    # + a title in the accent). The card itself is what tells the observer
    # where the group begins and ends when it is expanded.
    # @args: hue - the project's kind hue, or None for the app's accent
    # @return: a stylesheet for that header button
    accent = hue or C_ACCENT
    hover = composite(accent, "e6", over="#ffffff")   # +10% toward white
    return (f"QPushButton {{ background: transparent; border: none;"
            f" text-align: left; color: {accent}; padding: 8px 10px; }}"
            f"QPushButton:hover {{ color: {hover}; }}")


def block_card_style(hue=None):
    # The card a collapsible group lives in: the object card's own section
    # skin (a hairline border, a 10 px radius and a 3 px spine in the quiet
    # composite of the object's hue), so the two views share one voice and
    # the group has a visible end.
    # @args: hue - the project's kind hue, or None for the app's accent
    # @return: a stylesheet for the card frame
    accent = hue or C_ACCENT
    return (f"QFrame#sectionCard {{ background: {C_BASE};"
            f" border: 1px solid {C_LINE}; border-radius: 10px;"
            f" border-left: 3px solid {composite(accent, '70', over=C_BASE)};"
            f" }}")


def progress_style(hue):
    # A progress bar that fills in the object's hue: the run is this
    # project's, and the bar says so with the same colour the panel uses.
    # @args: hue - the project's kind hue
    # @return: a stylesheet for that QProgressBar
    return (f"QProgressBar {{ border: 1px solid {C_LINE}; border-radius: 3px;"
            f" background: {C_BASE}; text-align: center; }}"
            f"QProgressBar::chunk {{ background: {hue}; border-radius: 2px; }}")


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


def tint(color, alpha="18"):
    # @args: color - a #rrggbb hex; alpha - 2 hex digits (default "18" ≈ 10%)
    # @return: an #aarrggbb string for QSS. Qt reads 8-digit hexes
    #          alpha-FIRST, so the alpha goes in front — suffixing it would
    #          paint AA=RR, GG=GG, BB=BA…: a hue and opacity nobody asked
    #          for. Surfaces that stand over painted list text should use
    #          the opaque composite() instead.
    return "#" + alpha + color[1:]


def composite(color, alpha="18", over=C_BASE):
    # @args: color - a #rrggbb hue; alpha - 2 hex digits (default "18" ≈
    #        10%); over - the solid base the wash sits on
    # @return: a solid #rrggbb — the hue blended over the base. Use it for
    #          anything standing over a painted list item (row cards, icon
    #          tiles): QListView still paints the item's own text under the
    #          item widget, and a translucent fill would ghost it through.
    a = int(alpha, 16) / 255.0
    c = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    b = (int(over[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(
        int(round(x + a * (y - x))) for x, y in zip(b, c))


def row_skin(name, bg, edge, radius=6, spine=None):
    # @args: name - the row's objectName (anchors the QFrame#… selector);
    #        bg/edge - base fill and border ("transparent" for none);
    #        radius - the corner radius in px;
    #        spine - a colour for a 3 px left edge, or None. The projects
    #          list uses it to carry each row's kind hue, so the list reads
    #          as a colour map instead of a block of one shade.
    # @return: a row-skin stylesheet (base + hover). Every list in the app —
    #          tonight, projects, campaigns — hovers in this one voice, so a
    #          new row can't drift to its own shade.
    left = f" border-left: 3px solid {spine};" if spine else ""
    return (f"QFrame#{name} {{ background: {bg}; border-radius: {radius}px;"
            f" border: 1px solid {edge};{left} }}"
            f"QFrame#{name}:hover {{ background: {C_ROW_HOVER}; }}")


def tab_state_style(state, kind_color, active=False):
    # @args: state - one of "done" | "current" | "skipped" | "pending",
    #        kind_color - the project's accent (a KIND_COLORS hue); it tints
    #          the two live states,
    #        active - True for the page you are looking at (ADR-041): it
    #          is painted SOLID in the accent so "you are here" reads at
    #          a glance, whatever the step's state
    # @return: a stylesheet for ONE tab-bar button in the project masthead
    #          (ADR-041). The active tab shouts in the accent; the
    #          inactive ones keep the quiet state vocabulary (filled done,
    #          outlined current, dimmed skipped, plain pending) — they say
    #          where your steps are.
    if active:
        bg = composite(kind_color, "59", over=C_PANEL)
        edge = composite(kind_color, "cc", over=C_PANEL)
        fg = chip_text_for(bg)
    elif state == "done":
        bg = composite(kind_color, "33", over=C_PANEL)
        edge = composite(kind_color, "66", over=C_PANEL)
        fg = C_TEXT_DIM
    elif state == "current":
        bg = composite(kind_color, "1f", over=C_PANEL)
        edge = kind_color
        fg = C_TEXT
    elif state == "skipped":
        bg, edge, fg = C_DIM_FILL, C_LINE, C_TEXT_DIM
    else:  # pending
        bg, edge, fg = "transparent", C_EDGE, C_TEXT_DIM
    return (f"QPushButton {{ background: {bg}; color: {fg};"
            f" border: 1px solid {edge}; border-radius: 11px;"
            f" padding: 3px 12px; }}")


def kpi_tile_style(accent=None):
    # @args: accent - the hue for the tile's 3 px spine, or None for a
    #          neutral tile
    # @return: a stylesheet for ONE KPI tile of the object card's "tonight"
    #          strip (ADR-057). The spine keeps the app's list grammar (the
    #          hue carries the meaning); the fill stays the plain card base,
    #          because a tinted wash over the dark card read muddy every
    #          time we tried it (the same reason chip_style is solid).
    spine = f" border-left: 3px solid {accent};" if accent else ""
    return (f"QFrame#kpiTile {{ background: {C_BASE};"
            f" border: 1px solid {C_LINE}; border-radius: 8px;{spine} }}")


def section_card_style(accent):
    # @args: accent - the object's kind hue, carried by the card's spine
    # @return: a stylesheet for ONE parameter-section card of the object
    #          card (ADR-057). Same panel voice as the KPI tiles, so the
    #          dossier reads as one document; the spine is the quiet
    #          composite (like an unselected kind card), not the raw hue.
    return (f"QFrame#sectionCard {{ background: {C_BASE};"
            f" border: 1px solid {C_LINE}; border-radius: 10px;"
            f" border-left: 3px solid {composite(accent, '70', over=C_BASE)};"
            f" }}")


def kind_card_style(accent, selected=False):
    # @args: accent - the kind's KIND_COLORS hue; selected - whether the
    #          observer follows it right now
    # @return: a stylesheet for ONE card of the Welcome targets grid.
    #   Every card keeps a spine in its kind's hue, so the grid reads as a
    #   colour-coded map of the sky and not as a wall of checkboxes. The
    #   selected card is washed in the hue and edged with it; the quiet
    #   ones stay a hairline. The wash is a SOLID composite, never an
    #   alpha: over the panel an alpha hue reads muddy (the same reason
    #   chip_style is solid).
    if selected:
        bg = composite(accent, "24", over=C_BASE)
        edge = accent
        spine = accent
    else:
        bg = C_BASE
        edge = C_LINE
        spine = composite(accent, "70", over=C_BASE)
    return (f"QFrame#kindCard {{ background: {bg}; border: 1px solid {edge};"
            f" border-left: 3px solid {spine}; border-radius: 10px; }}"
            f"QFrame#kindCard:hover {{ background: {C_ROW_HOVER};"
            f" border: 1px solid {edge};"
            f" border-left: 3px solid {accent}; }}")


def _is_themed(app):
    # @args: app - the QApplication
    # @return: True when it already carries this theme. The marker lives on
    #          the app itself: comparing against a freshly built QPalette
    #          does not work (Qt resolves the roles on the way in, so the
    #          two never match) and neither does asking the style its name
    #          (a QStyle has none). The stylesheet is checked too, so an app
    #          whose sheet was replaced gets the theme back.
    return bool(getattr(app, "_nightscribe_themed", False)) \
        and app.styleSheet() == _QSS


def apply_theme(app):
    # Applies the NightScribe dark theme to a live QApplication:
    # Fusion base style, dark palette, and the global stylesheet.
    # Call once, right after the QApplication is created (app.py).
    #
    # It is IDEMPOTENT on purpose. Applying an app stylesheet re-polishes
    # EVERY live widget, and re-applying the very same one is far worse
    # than the first time: measured with 3880 widgets alive, the first
    # setStyleSheet() takes 0.75 s and the second 5.4 s (setStyle and
    # setPalette add ~0.37 s together). The unit tests theme the app once
    # per fixture, 57 times per run, with the windows of the previous ones
    # still alive; on the Windows runner (a single process, no xdist) that
    # grew past pytest-timeout's two minutes eleven times in a row and the
    # whole job died. Nothing to redo when the app already carries it.
    # @args: app - the QApplication
    # @return: None
    if _is_themed(app):
        return
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setStyleSheet(_QSS)
    app._nightscribe_themed = True


_QSS = f"""
/* ---- base ----------------------------------------------------------- */
* {{ font-size: 13px; }}

QMainWindow, QDialog {{ background: {C_BG}; color: {C_TEXT}; }}
QWidget {{ color: {C_TEXT}; }}

/* ---- buttons --------------------------------------------------------- */
QPushButton {{
    background: {C_PANEL}; color: {C_TEXT}; border: 1px solid {C_EDGE};
    border-radius: 4px; padding: 6px 16px;
}}
QPushButton:hover {{ background: {C_HOVER}; }}
QPushButton:pressed {{ background: {C_SEL}; }}
QPushButton:disabled {{ color: {C_TEXT_DIM}; background: {C_DIM_FILL}; }}
QPushButton:flat {{ background: transparent; }}
QPushButton:flat:hover {{ background: rgba(255,255,255,0.06); }}
/* small glyph buttons (28-32 px wide: the ↻ recompute, the × row
   removals, …): the global 6px/16px padding leaves them no content rect
   at all and the glyph clips away, so they carry compact="true" */
QPushButton[compact="true"] {{ padding: 2px 6px; }}
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
/* a styled combo / spinbox paints its own subcontrols: without an
   explicit image the arrows are simply never drawn */
QComboBox::down-arrow {{
    image: url("{ARROW_DOWN_SVG}"); width: 12px; height: 12px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{ARROW_UP_SVG}"); width: 10px; height: 10px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{ARROW_DOWN_SVG}"); width: 10px; height: 10px;
}}
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

/* ---- Interfaz 1.4: Welcome, the painted hero (ADR-005, ADR-026) --------
   The hero is a night sky: gui/widgets/welcome_sky.py paints the vector
   sky and tonight's real Moon inside it, so the frame here only keeps the
   border and a fill that matches the sky's top colour (the rounded
   corners of the sky widget show this fill, not a lighter seam). */
QFrame#welcomeHero {{
    background: #04060d; border: 1px solid {C_LINE}; border-radius: 14px;
}}
QLabel#welcomeWordmark {{ font-size: 30px; font-weight: 800;
                          letter-spacing: 8px; }}
QLabel#welcomeTag {{ color: #b9c2d6; font-size: 14px; }}
QLabel#welcomeLead {{ color: #9aa3ba; }}
/* The "this is a new version" badge, next to the report's title. */
QLabel#lbl_data_badge {{
    color: {C_ACCENT}; font-size: 10px; font-weight: 700;
    letter-spacing: 1px; padding: 3px 10px; border-radius: 9px;
    background: {composite(C_ACCENT, "3a", over="#0a1020")};
}}

/* The live "your night, now" panel that sits over the sky. A translucent
   dark panel, not a solid one: the stars must stay visible through it or
   the hero stops being a sky. */
QFrame#nightStrip {{
    background: rgba(9, 13, 24, 0.72);
    border: 1px solid rgba(90, 110, 150, 0.35);
    border-left: 3px solid {C_ACCENT}; border-radius: 10px;
}}
QLabel#lbl_night_icon {{ font-size: 22px; color: #cfd9ee; }}
QLabel#lbl_night_title {{ font-size: 10px; font-weight: 700;
                          letter-spacing: 1px; color: {C_ACCENT}; }}
QLabel#lbl_night_window {{ color: #e2e7f2; }}
QLabel#lbl_night_moon, QLabel#lbl_night_planets {{
    color: #97a0b8; font-size: 12px;
}}
QPushButton#btn_night_set {{
    background: rgba(106, 176, 255, 0.12); color: {C_ACCENT};
    border: 1px solid rgba(106, 176, 255, 0.45); border-radius: 6px;
    padding: 5px 12px;
}}
QPushButton#btn_night_set:hover {{ background: rgba(106, 176, 255, 0.22); }}

/* The stepper as a rail: numbered nodes joined by a line that fills as you
   advance (the code flips the [state] property; the colours live here). */
QToolButton#btn_step_obs, QToolButton#btn_step_kinds,
QToolButton#btn_step_data {{
    background: {C_PANEL}; border: 1px solid {C_LINE}; border-radius: 15px;
    padding: 5px 16px; color: {C_TEXT_DIM};
}}
QToolButton#btn_step_obs:hover, QToolButton#btn_step_kinds:hover,
QToolButton#btn_step_data:hover {{ background: {C_HOVER}; }}
QToolButton#btn_step_obs:checked, QToolButton#btn_step_kinds:checked,
QToolButton#btn_step_data:checked {{
    border-color: {C_ACCENT}; color: {C_TEXT}; background: {C_HOVER};
}}
QToolButton#btn_step_obs[state="done"],
QToolButton#btn_step_kinds[state="done"],
QToolButton#btn_step_data[state="done"] {{
    border-color: {C_GOOD}; color: {C_TEXT};
}}
QFrame#rail_sep1, QFrame#rail_sep2 {{
    background: {C_LINE}; border: none; margin: 0 6px;
}}
QFrame#rail_sep1[state="done"], QFrame#rail_sep2[state="done"] {{
    background: {C_GOOD};
}}

QFrame#panel_obs, QFrame#panel_kinds, QFrame#panel_data {{
    background: {C_BASE}; border: 1px solid {C_LINE}; border-radius: 12px;
}}
QLabel#lbl_obs_title, QLabel#lbl_kinds_title, QLabel#lbl_data_title {{
    font-size: 16px; font-weight: 700;
}}
QLabel#lbl_obs_sub, QLabel#lbl_kinds_sub, QLabel#lbl_data_sub,
QLabel#lbl_site_status, QLabel#lbl_site_privacy, QLabel#lbl_kinds_rule,
QLabel#lbl_data_rule {{ color: {C_TEXT_DIM}; }}
QLabel#lbl_site_privacy, QLabel#lbl_kinds_rule, QLabel#lbl_data_rule {{
    font-size: 11px;
}}
QLabel#lbl_kinds_count {{
    color: {C_ACCENT}; font-weight: 700; font-size: 11px;
    background: {tint(C_ACCENT, "22")}; border-radius: 8px;
    padding: 2px 9px;
}}
QLabel#lbl_data_icon {{ font-size: 26px; color: {C_GOOD}; }}

/* The three doors at the bottom. */
QFrame#wcard1, QFrame#wcard2, QFrame#wcard3 {{
    background: {C_BASE}; border: 1px solid {C_LINE}; border-radius: 10px;
}}
QFrame#wcard1:hover, QFrame#wcard2:hover, QFrame#wcard3:hover {{
    background: {C_PANEL}; border: 1px solid {C_EDGE};
}}
QLabel#lbl_card1_icon, QLabel#lbl_card2_icon, QLabel#lbl_card3_icon {{
    color: {C_ACCENT}; font-size: 15px;
}}
QLabel#lbl_card1_title, QLabel#lbl_card2_title, QLabel#lbl_card3_title {{
    font-weight: 700;
}}
QLabel#lbl_card1_body, QLabel#lbl_card2_body, QLabel#lbl_card3_body {{
    color: #c7cbd9;
}}
QPushButton#btn_card2_guide, QPushButton#btn_card3_skycal {{
    color: {C_ACCENT}; text-align: left; padding: 0; border: none;
    background: transparent;
}}
QPushButton#btn_card2_guide:hover, QPushButton#btn_card3_skycal:hover {{
    color: #9ccbff;
}}

QPushButton#btn_create {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2f6fd0, stop:1 #2559a8);
    border: 1px solid #4d86e0; border-radius: 12px;
    padding: 12px 32px; font-size: 15px; font-weight: 700; color: #ffffff;
}}
QPushButton#btn_create:hover {{ background: #3579dd; }}
QPushButton#btn_create:disabled {{
    background: {C_DIM_FILL}; border: 1px solid {C_LINE};
    color: {C_TEXT_DIM};
}}
/* THE action of a panel, whichever button happens to carry it today: on an
   update the report's own "got it" is the one and only way forward, and a
   default-sized button would undersell it. */
QPushButton[primary="true"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2f6fd0, stop:1 #2559a8);
    border: 1px solid #4d86e0; border-radius: 12px;
    padding: 11px 28px; font-size: 15px; font-weight: 700; color: #ffffff;
}}
QPushButton[primary="true"]:hover {{ background: #3579dd; }}
QLabel#lbl_cta_sub {{ color: {C_TEXT_DIM}; }}
/* The quiet escape hatch. border/background are set explicitly: Qt's
   "flat" property is ignored the moment a stylesheet gives the button a
   background, so the flat look has to be spelled out here. */
QPushButton#btn_skip {{
    background: transparent; border: none; color: {C_TEXT_DIM};
    padding: 6px 8px;
}}
QPushButton#btn_skip:hover {{ color: {C_ACCENT}; background: transparent; }}

QFrame#homeHead {{ background: transparent; }}
/* Interfaz 1.7: the "next" action, as a slim band instead of a group box
   (the frame and its title cost 20 px of a page that has none to spare) */
/* the campaign summary: one wrapped sentence, so a labelled band and not
   a group box with a title of its own */
/* Interfaz 1.7: the parameters block of the object card (a frame now, not
   a group box) and its table: the explanations wrap to two or three lines,
   so the cell padding is what decides whether four rows fit or six. */
QFrame#grp_params {{
    background: {C_BASE}; border: 1px solid {C_LINE}; border-radius: 8px;
}}
QLabel#lbl_params_title {{ font-weight: 700; }}
QFrame#grp_params QTableWidget {{ border: none; }}
QFrame#grp_params QTableWidget::item {{ padding: 2px 6px; }}
QFrame#fu_campaign_summary {{
    background: {C_BASE}; border: 1px solid {C_LINE}; border-radius: 8px;
}}
QFrame#nextBand {{
    background: {C_BASE}; border: 1px solid {C_LINE};
    border-left: 3px solid {C_ACCENT}; border-radius: 8px;
}}
/* Interfaz 1.6: the two halves of the projects view. The list stops being
   a QGroupBox (a bordered box inside the page was a box inside a box); it
   is a panel now, and the splitter handle between the two is a hairline
   that lights up under the cursor. */
QGroupBox#projectsListPanel {{
    background: {C_BASE}; border: 1px solid {C_LINE}; border-radius: 10px;
    margin-top: 0; padding-top: 0;
}}
QGroupBox#projectsListPanel::title {{ padding: 0; }}
QFrame#projectsDetailPanel {{ background: transparent; border: none; }}
QSplitter#projectsSplit::handle {{ background: {C_LINE}; }}
QSplitter#projectsSplit::handle:hover {{ background: {C_ACCENT}; }}
/* the night panel's way in to a new project: quiet, because the resting
   pane should not shout, but clearly a button */
QLabel#nightHead {{
    color: {C_ACCENT}; font-size: 10px; font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#nightLine {{ color: #c7cbd9; }}
/* the invitation painted on the resting sky (ADR-055): a headline and a
   dim hint, both readable because the SVG already darkens that half */
QLabel#restingHead {{ color: {C_TEXT}; font-size: 15px; font-weight: 600; }}
QLabel#restingHint {{ color: {C_TEXT_DIM}; font-size: 12px; }}
QPushButton#nightCta {{
    background: rgba(106, 176, 255, 0.10); color: {C_ACCENT};
    border: 1px solid rgba(106, 176, 255, 0.40); border-radius: 8px;
    padding: 9px 16px; font-weight: 600;
}}
QPushButton#nightCta:hover {{ background: rgba(106, 176, 255, 0.20); }}
/* the navigation sky bar: quiet by design (it is ambient information, not
   a call to action) but the Moon is drawn, not glyphed */
QLabel#skyMoon {{ color: #d7dce8; font-size: 12px; }}
QLabel#skyWhen {{ color: #c7cbd9; font-size: 12px; }}
QLabel#skyPlanets {{ color: {C_TEXT_DIM}; font-size: 12px; }}
QPushButton#skyCalendar {{
    color: {C_ACCENT}; background: transparent; border: none; padding: 2px 6px;
}}
QPushButton#skyCalendar:hover {{ color: #9ccbff; }}
QLabel#homeTitle {{ font-size: 19px; font-weight: 700; }}
QPushButton#newTile {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2f6fd0, stop:1 #2559a8);
    border: 1px solid #4d86e0; border-radius: 10px;
    padding: 8px 18px; color: #ffffff; font-weight: 700;
}}
QPushButton#newTile:hover {{ background: #3579dd; }}
QFrame#skyBand {{
    background: {C_BASE}; border: 1px solid {C_LINE};
    border-left: 3px solid {C_ACCENT}; border-radius: 8px;
}}
QFrame#cadenceBand {{
    background: {C_BASE}; border: 1px solid {C_LINE};
    border-left: 3px solid {C_WARN}; border-radius: 8px;
}}
QLabel#bandHead {{ font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QFrame#campaignStrip {{
    background: {C_BASE}; border: 1px solid {C_LINE}; border-radius: 8px;
}}
QWidget#attentionBlock {{
    background: {C_BASE}; border: 1px solid {C_LINE};
    border-left: 3px solid {C_WARN}; border-radius: 8px;
}}
"""
