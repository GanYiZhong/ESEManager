"""The packaged self-test must start the real window and exit cleanly."""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_selftest_starts_main_window(tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "src", "ese_qt.py"), "--selftest"],
                       capture_output=True, text=True, timeout=120, env=env, cwd=str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SELFTEST_OK" in r.stdout
