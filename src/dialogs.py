"""About, release-notes and "What's new" dialogs (theme-aware, resizable)."""

import os
import platform
import sys

from PySide6.QtCore import Qt, QUrl, qVersion
from PySide6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QTextBrowser, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout)

import core
import theme
from appconfig import APP_DIR, APP_VERSION, GITHUB_REPO, RELEASES_URL
from models import human_size
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


class CleanupDialog(QDialog):
    """Groups of leftovers in the download folder with checkboxes. Only stale
    .part files start checked; the caller moves selected_items() to the trash."""

    GROUPS = (("orphans", "cleanup_g_orphan"), ("strays", "cleanup_g_stray"),
              ("parts", "cleanup_g_part"), ("empty", "cleanup_g_empty"))

    def __init__(self, parent, tr, report):
        super().__init__(parent)
        self.tr_ = tr
        self.setWindowTitle(tr("cleanup_title"))
        self.resize(680, 520)
        lay = QVBoxLayout(self)
        intro = QLabel(tr("cleanup_intro"))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        lay.addWidget(self.tree, 1)
        for key, label in self.GROUPS:
            items = report.get(key, [])
            if not items:
                continue
            total = sum(i["size"] for i in items)
            top = QTreeWidgetItem(self.tree, [f"{tr(label)}  ({len(items)}, {human_size(total)})"])
            top.setFlags(top.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            for it in items:
                text = it["rel"] if it["kind"] == "empty" \
                    else f"{it['rel']}  ({human_size(it['size'])})"
                if it["kind"] == "part":
                    text += "  " + tr("cleanup_age", t=self._age(it["age"]))
                child = QTreeWidgetItem(top, [text])
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setData(0, Qt.UserRole, it)
                child.setToolTip(0, it["path"])
                child.setCheckState(0, Qt.Checked if core.cleanup_default_selection(it)
                                    else Qt.Unchecked)
            top.setExpanded(True)
        cats = report.get("categories", {})
        sizes = ", ".join(f"{c} {human_size(v['size'])}" for c, v in sorted(cats.items()))
        self.cat_label = QLabel(tr("cleanup_cat_sizes", s=sizes))
        self.cat_label.setWordWrap(True)
        self.cat_label.setStyleSheet(theme.muted_label_qss())
        lay.addWidget(self.cat_label)
        self.summary = QLabel()
        lay.addWidget(self.summary)
        self.bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.bb.button(QDialogButtonBox.Ok).setText(tr("cleanup_btn"))
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        lay.addWidget(self.bb)
        self.tree.itemChanged.connect(lambda *_: self._update())
        self._update()

    def _age(self, sec):
        if sec >= 86400:
            return self.tr_("cleanup_age_d", n=int(sec // 86400))
        return self.tr_("cleanup_age_h", n=int(sec // 3600))

    def selected_items(self):
        out = []
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                c = top.child(j)
                if c.checkState(0) == Qt.Checked:
                    out.append(c.data(0, Qt.UserRole))
        return out

    def _update(self):
        sel = self.selected_items()
        self.summary.setText(self.tr_("cleanup_selected", n=len(sel),
                                      size=human_size(sum(i["size"] for i in sel))))
        self.bb.button(QDialogButtonBox.Ok).setEnabled(bool(sel))
