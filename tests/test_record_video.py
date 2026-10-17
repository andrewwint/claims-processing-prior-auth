"""The video script: PM-approved captions held long enough, the video kept outside the repo,
and the password never taken from anywhere but the environment."""

import subprocess
import sys
from pathlib import Path

from scripts import record_video as rv

ROOT = Path(__file__).resolve().parent.parent


def test_every_caption_is_held_long_enough():
    assert rv.CAPTIONS["title"][1] == 4
    assert rv.CAPTIONS["packet"][1] >= 8
    for key, (text, hold) in rv.CAPTIONS.items():
        assert text.strip() and (key == "title" or hold >= 5), key


def test_the_video_states_it_is_scripted():
    assert "Scripted run recorded with Playwright." in rv.CAPTIONS["title"][0]


def test_refuses_an_output_folder_inside_the_repo():
    out = subprocess.run([sys.executable, "-m", "scripts.record_video", str(ROOT / "video")], cwd=ROOT,
                         capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert out.returncode == 2 and "outside the repository" in out.stderr


def test_refuses_without_the_password_variable(tmp_path):
    out = subprocess.run([sys.executable, "-m", "scripts.record_video", str(tmp_path / "v")], cwd=ROOT,
                         capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert out.returncode == 2 and "PA_VIDEO_PASSWORD" in out.stderr


def _row(c, status):
    return f'<td>{c}</td><td class="{status.split()[0]}">{status}</td>'


def test_packet_view_guard_accepts_the_captioned_state():
    page = "run R1 " + _row("C1", "Met") + _row("C2", "Met") + _row("C3", "Not found")
    rv.check_packet_view(page, "R1")


def test_packet_view_guard_rejects_the_bad_take():
    import pytest
    bad = ("run R1 The stored packet is not the one this run recommended "
           + _row("C1", "Not found") + _row("C2", "Not found") + _row("C3", "Not found"))
    with pytest.raises(rv.PacketViewMismatch):
        rv.check_packet_view(bad, "R1")
    with pytest.raises(rv.PacketViewMismatch):  # a different run on screen
        rv.check_packet_view("run R0 " + _row("C1", "Met") + _row("C2", "Met") + _row("C3", "Not found"), "R1")
