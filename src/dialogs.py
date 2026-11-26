"""About, release-notes and "What's new" dialogs (theme-aware, resizable)."""

import os
import platform
import sys

from PySide6.QtCore import Qt, QUrl, qVersion
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QTextBrowser, QVBoxLayout)

import core
import theme
from appconfig import APP_DIR, APP_VERSION, GITHUB_REPO, RELEASES_URL
from notify import resource_path

LINKS = (
    ("GitHub", f"https://github.com/{GITHUB_REPO}"),
    ("Releases", RELEASES_URL),
    ("ESE", "https://ese.tjadataba.se/ESE/ESE"),
    ("git.taiko.ac", "https://git.taiko.ac/zdon/ESE"),
)
LOG_NAME = "ESEManager.log"
NOTES_MAX_HEIGHT = 360


def log_path():
    return os.path.join(APP_DIR, LOG_NAME)


def open_local(path):
    """Open a file or folder with the OS default handler; a missing log opens its folder."""
    if not os.path.exists(path):
        path = os.path.dirname(path) or APP_DIR
    return QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def diagnostics_text(db_version=None):
    try:
        import PySide6
        pyside = PySide6.__version__
    except Exception:
        pyside = "?"
    return "\n".join([
        f"ESEManager {APP_VERSION}",
        f"OS: {platform.platform()}",
        f"Python: {platform.python_version()}",
        f"Qt: {qVersion()} (PySide6 {pyside})",
        f"Download source: {core._download_source}",
        f"DB version: {db_version or '-'}",
        f"Frozen: {bool(getattr(sys, 'frozen', False))}",
    ])


def notes_browser(markdown, parent=None):
    """Scrollable, link-opening Markdown view with a capped height."""
    tb = QTextBrowser(parent)
    tb.setOpenExternalLinks(True)
    tb.setMaximumHeight(NOTES_MAX_HEIGHT)
    tb.setMinimumHeight(120)
    tb.setMarkdown(markdown)
    return tb


class AboutDialog(QDialog):
    def __init__(self, parent, tr, db_version=None):
        super().__init__(parent)
        self.tr_ = tr
        self.db_version = db_version
        self.setWindowTitle(tr("about_title"))
        self.resize(480, 380)
        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        icon = QLabel()
        pm = QPixmap(resource_path("assets", "icon.png"))
        if not pm.isNull():
            icon.setPixmap(pm.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        head.addWidget(icon)
        name = QLabel(f"<b style='font-size:16pt'>ESEManager</b><br>"
                      f"{tr('about_version')} {APP_VERSION}")
        head.addWidget(name, 1)
        lay.addLayout(head)
        links = QLabel(" · ".join(f'<a href="{u}">{n}</a>' for n, u in LINKS))
        links.setOpenExternalLinks(True)
        links.setWordWrap(True)
        lay.addWidget(links)
        grid = QGridLayout()
        self.paths = []
        for row, (key, path) in enumerate(((tr("about_data_dir"), APP_DIR),
                                           (tr("about_log"), log_path()))):
            grid.addWidget(QLabel(key), row, 0)
            lbl = QLabel(path)
            lbl.setToolTip(path)   # no word wrap: a path has no spaces to break at
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lbl.setStyleSheet(theme.muted_label_qss())
            grid.addWidget(lbl, row, 1)
            b = QPushButton(tr("about_open"))
            b.clicked.connect(lambda _=False, p=path: open_local(p))
            grid.addWidget(b, row, 2)
            self.paths.append((lbl, b))
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        lay.addStretch(1)
        btns = QHBoxLayout()
        self.copy_btn = QPushButton(tr("about_copy_diag"))
        self.copy_btn.clicked.connect(self.copy_diagnostics)
        btns.addWidget(self.copy_btn)
        btns.addStretch(1)
        close = QPushButton(tr("about_close"))
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        lay.addLayout(btns)

    def copy_diagnostics(self):
        QGuiApplication.clipboard().setText(diagnostics_text(self.db_version))
        self.copy_btn.setText(self.tr_("about_copied"))


class ReleaseNotesDialog(QDialog):
    """Update confirmation showing the new version's release notes (Yes / No)."""

    def __init__(self, parent, tr, message, notes):
        super().__init__(parent)
        self.setWindowTitle(tr("upd_app_title"))
        self.resize(560, 460)
        lay = QVBoxLayout(self)
        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        self.browser = notes_browser(notes or tr("whatsnew_none"), self)
        lay.addWidget(self.browser, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Yes | QDialogButtonBox.No)
        bb.button(QDialogButtonBox.Yes).clicked.connect(self.accept)
        bb.button(QDialogButtonBox.No).clicked.connect(self.reject)
        lay.addWidget(bb)


class WhatsNewDialog(QDialog):
    """Non-blocking 'What's new in vX' window."""

    def __init__(self, parent, tr, tag, notes):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(tr("whatsnew_title", v=tag))
        self.resize(520, 420)
        lay = QVBoxLayout(self)
        self.browser = notes_browser(notes or tr("whatsnew_none"), self)
        lay.addWidget(self.browser, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        b = QPushButton(tr("about_close"))
        b.clicked.connect(self.close)
        row.addWidget(b)
        lay.addLayout(row)
