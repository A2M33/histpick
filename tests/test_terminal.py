"""Drive the real picker through a pseudo-terminal. POSIX only: Windows has no pty."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="needs a POSIX pty")

SRC = str(Path(__file__).resolve().parent.parent / "src")
CLEAR = b"\x1b[2J"  # the picker clears the screen once per frame


class Pty:
    def __init__(self, args, env, cwd):
        import pty

        self.master, slave = pty.openpty()
        self.proc = subprocess.Popen([sys.executable, "-m", "histpick", *args], stdin=slave, stdout=slave,
                                     stderr=slave, env=env, cwd=cwd, start_new_session=True)
        os.close(slave)
        self.out = b""

    def pump(self, until, timeout=10.0):
        import select

        end = time.monotonic() + timeout
        while not until() and time.monotonic() < end:
            if select.select([self.master], [], [], 0.05)[0]:
                try:
                    chunk = os.read(self.master, 4096)
                except OSError:  # Linux raises EIO once the child has exited
                    chunk = b""
                if not chunk:
                    return
                self.out += chunk

    def key(self, data: bytes):
        frames = self.out.count(CLEAR)
        os.write(self.master, data)
        self.pump(lambda: self.out.count(CLEAR) > frames)

    def finish(self, data: bytes) -> int:
        os.write(self.master, data)
        self.pump(lambda: self.proc.poll() is not None)
        code = self.proc.wait(timeout=10)
        os.close(self.master)
        return code


@pytest.fixture
def term(tmp_path):
    hist = tmp_path / ".bash_history"
    hist.write_text("echo one\necho two\necho three\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("PSModulePath", "MSYSTEM")}
    env.update(HOME=str(tmp_path), HISTFILE=str(hist), SHELL="/bin/bash", TERM="xterm",
               COLUMNS="80", LINES="24", PYTHONPATH=SRC)

    def start(*args):
        t = Pty(["--shell", "bash", *args], env, tmp_path)
        t.pump(lambda: b"filter:" in t.out)
        assert b"filter:" in t.out, t.out
        return t

    return start


def test_arrow_keys_move_instead_of_cancelling(term, tmp_path):
    t = term("-o", "out")
    t.key(b"\x1b[B")  # down: from "echo three" to "echo two"
    t.key(b"\t")
    t.key(b"\r")  # review screen
    assert b"review" in t.out
    assert t.finish(b"\r") == 0, t.out
    script = (tmp_path / "out.sh").read_text(encoding="utf-8")
    assert "echo two" in script
    assert "echo three" not in script


def test_key_reader_decodes_escape_sequences():
    import pty

    from histpick import picker

    master, slave = pty.openpty()
    try:
        with picker._Keys(slave) as keys:
            for data, want in [(b"\x1b[A", picker.UP), (b"\x1bOB", picker.DOWN), (b"\x1b[5~", picker.PGUP),
                               (b"\x1b[1;5H", picker.HOME), (b"\x1b[1;5A", picker.MOVE_UP),
                               (b"\x1b[D", picker.LEFT), (b"\x1b[C", picker.RIGHT), (b"\x1b[3~", picker.DELETE),
                               (b"\x15", picker.CTRL_U), (b" ", " "),
                               ("é".encode(), "é"), (b"x", "x")]:
                os.write(master, data)
                assert keys.read() == want, data
            os.write(master, b"\x1b")
            assert keys.read() == picker.ESC
    finally:
        os.close(master)
        os.close(slave)


def test_review_screen_reorders_before_saving(term, tmp_path):
    t = term("-o", "out")
    t.key(b"\t")  # echo three
    t.key(b"\t")  # echo two
    t.key(b"\r")  # review: echo two, echo three
    t.key(b"d")  # move echo two below echo three
    assert t.finish(b"\r") == 0, t.out
    script = (tmp_path / "out.sh").read_text(encoding="utf-8")
    assert script.index("echo three") < script.index("echo two")
