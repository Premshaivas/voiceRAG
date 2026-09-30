from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from backend.video_routes import _download_video


def test_youtube_download_does_not_simulate_and_returns_audio(tmp_path, monkeypatch):
    def run(args, **kwargs):
        assert "--no-simulate" in args
        (tmp_path / "demo.mp3").write_bytes(b"audio")
        return SimpleNamespace(returncode=0, stdout="Demo video title\n", stderr="")

    monkeypatch.setattr(subprocess, "run", run)

    path, title = _download_video("https://youtu.be/demo", str(tmp_path))

    assert path == str(tmp_path / "demo.mp3")
    assert title == "Demo video title"


def test_youtube_download_failure_does_not_fetch_watch_page(tmp_path, monkeypatch):
    def run(args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="video unavailable")

    def forbidden_urlopen(*args, **kwargs):
        raise AssertionError("A YouTube watch page must not be passed off as a media download")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("backend.video_routes.urlopen", forbidden_urlopen)

    with pytest.raises(RuntimeError, match="Could not download the YouTube video"):
        _download_video("https://www.youtube.com/watch?v=demo", str(tmp_path))
