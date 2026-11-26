"""The window's two button rows collapse instead of fixing a huge minimum width."""

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QVBoxLayout, QWidget

import appconfig
import core
import ese_qt
import workers
from responsive import ResponsiveRow


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    for mod in (appconfig, ese_qt, workers, core):
        for name, val in (("DB_PATH", tmp_path / "ese_songs.db"),
                          ("LOCAL_DB_PATH", tmp_path / "ese_local.db"),
                          ("CONFIG_FILE", tmp_path / "config.toml"),
                          ("VERSION_FILE", tmp_path / "version.txt"),
                          ("NEW_SONGS_FILE", tmp_path / "new_songs.json")):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, str(val))
    monkeypatch.setattr(ese_qt, "APP_DIR", str(tmp_path))
    monkeypatch.setattr(appconfig, "APP_DIR", str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    w = ese_qt.MainWindow()
    yield w
    from conftest import dispose_window
    dispose_window(w)


def _settle(w):
    w.layout().invalidate()
    QApplication.processEvents()


@pytest.mark.parametrize("lang", ["zh_TW", "en", "ja"])
def test_minimum_width_fits_small_screens(window, lang):
    window.lang = lang
    window.build_ui()
    window.show()
    _settle(window)
    assert window.minimumSizeHint().width() <= 1000


def test_rows_collapse_and_expand_with_width(window):
    window.lang = "en"
    window.build_ui()
    window.show()
    for row in (window.top_row, window.bottom_row):
        need = row.needed_widths()
        assert need == sorted(need, reverse=True)
        row.update_mode(need[0] + 40)
        assert row.mode == 0
        row.update_mode(need[-1])
        assert row.mode == row.mode_count - 1
    # top row: first step = icon-only maintenance buttons (accessible name stays)
    top = window.top_row
    top.update_mode(top.needed_widths()[1] + 30)
    assert top.mode == 1
    assert window.missing_btn.text() == ""
    assert window.missing_btn.accessibleName()
    assert window.missing_btn.toolTip()
    # then overflow: check missing / updates move into the "..." menu
    top.update_mode(top.needed_widths()[2] + 30)
    assert top.mode == 2
    assert window.missing_btn.isHidden() and not window.more_btn.isHidden()
    assert len(window.more_menu.actions()) == 2
    # primary controls always visible
    assert not window.search_edit.isHidden() and not window.download_btn.isHidden()
    assert window.download_btn.text()
    # fully expanded again restores text and hides the overflow button
    top.update_mode(top.needed_widths()[0] + 40)
    assert top.mode == 0
    assert window.missing_btn.text() and window.more_btn.isHidden()


def test_bottom_row_moves_select_all_into_menu(window):
    window.lang = "en"
    window.build_ui()
    window.show()
    row = window.bottom_row
    need = row.needed_widths()
    row.update_mode(need[0] + 40)
    assert not window.selall_btn.isHidden()
    assert not window.act_sel_all.isVisible()
    row.update_mode(need[-1])
    assert window.selall_btn.isHidden() and window.deselall_btn.isHidden()
    assert window.act_sel_all.isVisible() and window.act_desel_all.isVisible()
    assert not window.download_btn.isHidden() and window.download_btn.text()
    assert not window.pause_btn.isHidden() and window.pause_btn.text()
    assert not window.stop_btn.isHidden() and window.stop_btn.text()


def test_hysteresis_prevents_flicker(qapp):
    holder = QWidget()
    QVBoxLayout(holder).addWidget(row := ResponsiveRow())
    a, b = QPushButton("Alpha button"), QPushButton("Beta button")
    row.row_layout().addWidget(a)
    row.row_layout().addWidget(b)
    row.add_step(lambda on: b.setVisible(not on))
    holder.show()
    need = row.needed_widths()
    assert need[1] < need[0]
    holder.resize(need[1] + 20, 60)
    assert row.mode == 1
    holder.resize(need[0] + 1 + 20, 60)      # fits, but within the hysteresis band
    assert row.mode == 1
    holder.resize(need[0] + 100 + 20, 60)
    assert row.mode == 0
    holder.resize(need[0] - 1 + 20, 60)
    assert row.mode == 1
    holder.close()
