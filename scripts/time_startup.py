"""Startup timing: import ese_qt, MainWindow construction, time until a full list
is shown. Run: QT_QPA_PLATFORM=offscreen python scripts/time_startup.py"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
t0 = time.perf_counter()
import ese_qt  # noqa: E402
t1 = time.perf_counter()
from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication(sys.argv)
t2 = time.perf_counter()
w = ese_qt.MainWindow()
w.show()
t3 = time.perf_counter()
n0 = w.song_model.rowCount()
if not n0:
    w.show_all()
while not w.song_model.rowCount() and time.perf_counter() - t3 < 30:
    app.processEvents()
t4 = time.perf_counter()
print(f"import ese_qt     {t1-t0:.3f}s")
print(f"QApplication      {t2-t1:.3f}s")
print(f"MainWindow+show   {t3-t2:.3f}s (rows at show: {n0})")
print(f"list populated    {t4-t3:.3f}s after show ({w.song_model.rowCount()} rows)")
print(f"TOTAL to list     {t4-t0:.3f}s")
sys.stdout.flush()
w._closing = True
os._exit(0)
