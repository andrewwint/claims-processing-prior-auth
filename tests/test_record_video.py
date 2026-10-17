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
