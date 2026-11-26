"""Benchmark a huge batch download through the real MainWindow path.

    QT_QPA_PLATFORM=offscreen python scripts/bench_download.py [N_SONGS] [FILES_PER_SONG]

Serves tiny fake files from a local http.server and reports total time, peak
memory (RSS via psutil) and UI responsiveness (max gap between ticks of a
16 ms probe timer).
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402
import appconfig, ese_qt, core, workers  # noqa: E402,E401

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3200
PER = int(sys.argv[2]) if len(sys.argv) > 2 else 2

tmp = tempfile.mkdtemp()
body = b"x" * 64


SERVER = r"""
import http.server, sys
body = b"x" * 64
class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
srv.daemon_threads = True
print(srv.server_address[1], flush=True)
srv.serve_forever()
"""
# The fake server runs in its own process so its threads do not compete with
# the app for the GIL.
import subprocess  # noqa: E402
srv = subprocess.Popen([sys.executable, "-c", SERVER], stdout=subprocess.PIPE, text=True)
base = f"http://127.0.0.1:{int(srv.stdout.readline())}/"

files = []
for i in range(N):
    song = {"song_name": f"Song {i}", "files": []}
    for j in range(PER):
        fp = f"Cat/Song{i}/f{j}.tja"
        song["files"].append({"filename": f"f{j}.tja", "file_path": fp,
                              "download_url": base + fp})
    files += [(song, f) for f in song["files"]]

for mod in (appconfig, ese_qt, workers, core):
    for name, val in (("DB_PATH", "ese_songs.db"), ("LOCAL_DB_PATH", "ese_local.db"),
                      ("CONFIG_FILE", "config.toml"), ("VERSION_FILE", "version.txt")):
        if hasattr(mod, name):
            setattr(mod, name, os.path.join(tmp, val))
ese_qt.APP_DIR = appconfig.APP_DIR = tmp
for n in ("question", "information", "warning"):
    setattr(QMessageBox, n, lambda *a, **k: QMessageBox.Yes)

app = QApplication([])
w = ese_qt.MainWindow()
w.dir_edit.setText(os.path.join(tmp, "out"))
w.workers_spin.setValue(16)
w.show()
w._show_summary = lambda *a, **k: None   # never block on the modal summary
w.notifier.notify = lambda *a, **k: None

import psutil  # noqa: E402
proc = psutil.Process()
rss0 = proc.memory_info().rss
peak = [rss0]
gaps, last, stamps = [], [time.perf_counter()], []


def probe():
    now = time.perf_counter()
    gaps.append(now - last[0])
    stamps.append(now)
    last[0] = now
    peak[0] = max(peak[0], proc.memory_info().rss)


pt = QTimer()
pt.setInterval(16)
pt.timeout.connect(probe)
pt.start()

done = []
t0 = time.perf_counter()
w.start_download(files)
t_start = time.perf_counter() - t0
last[0] = time.perf_counter()
w.dl_thread.finished_all.connect(lambda *a: done.append(a))
from PySide6.QtCore import QEventLoop  # noqa: E402
loop = QEventLoop()
w.dl_thread.finished_all.connect(lambda *a: QTimer.singleShot(0, loop.quit))
if not done:
    loop.exec()
total = time.perf_counter() - t0
for _ in range(20):
    app.processEvents()
worst = max(range(len(gaps)), key=gaps.__getitem__)
worst_at = stamps[worst] - t0
gaps.sort()
print(f"files={len(files)} result(dl,skip,fail,total)={done[0]}")
print(f"start_download blocked UI: {t_start*1000:.0f} ms")
print(f"total: {total:.2f} s ({len(files)/total:.0f} files/s)")
print(f"peak RSS +{(peak[0]-rss0)/1e6:.0f} MB")
print(f"UI gap max {gaps[-1]*1000:.0f} ms, p99 {gaps[int(len(gaps)*.99)]*1000:.0f} ms, "
      f"ticks {len(gaps)}; worst gap ended at t={worst_at:.2f}s")
print(f"log lines in view: {w.log_view.blockCount()}")
srv.kill()
sys.stdout.flush()
os._exit(0)
