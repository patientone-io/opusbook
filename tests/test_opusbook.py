"""Unit + integration tests for opusbook (mocked ffmpeg/ffprobe)."""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import opusbook as ob


# ── formatting helpers ──────────────────────────────────────────────
def test_fmt_mb():
    assert ob.fmt_mb(0.5) == "0.50 MB"
    assert ob.fmt_mb(1500) == "1.46 GB"


def test_fmt_duration():
    assert ob.fmt_duration(0) == "—"
    assert ob.fmt_duration(-5) == "—"
    assert ob.fmt_duration(45) == "45s"
    assert ob.fmt_duration(185) == "3m 5s"
    assert ob.fmt_duration(7385) == "2h 3m 5s"


def test_fmt_time_code():
    assert ob.fmt_time_code(65) == "01:05"
    assert ob.fmt_time_code(3725) == "01:02:05"


def test_ratio_color():
    assert ob.ratio_color(75) == "bright_green bold"
    assert ob.ratio_color(55) == "green"
    assert ob.ratio_color(35) == "yellow"
    assert ob.ratio_color(10) == "red"


# ── data types ──────────────────────────────────────────────────────
def test_conversion_result_math():
    r = ob.ConversionResult(
        name="a.mp3", source=Path("a.mp3"), output=Path("a.opus"),
        src_bytes=100_000_000, opus_bytes=30_000_000,
        duration_s=5.0, status="ok", audio_duration=3600.0,
    )
    assert r.saved_bytes == 70_000_000
    assert r.ratio == pytest.approx(70.0)
    assert r.src_mb == pytest.approx(100_000_000 / 1_048_576)
    # backward-compat aliases
    assert r.mp3_bytes == r.src_bytes
    assert r.mp3_mb == pytest.approx(r.src_mb)


def test_stats_speed_wall_clock():
    s = ob.Stats(elapsed_s=10.0)
    s.results.append(ob.ConversionResult(
        name="a", source=Path("a"), output=Path("b"),
        src_bytes=int(20 * 1_048_576), opus_bytes=10, duration_s=2.0,
        status="ok", audio_duration=100,
    ))
    assert s.avg_speed_mb == pytest.approx(2.0)
    # fallback when elapsed not set
    s2 = ob.Stats()
    s2.results.append(ob.ConversionResult(
        name="a", source=Path("a"), output=Path("b"),
        src_bytes=int(20 * 1_048_576), opus_bytes=10, duration_s=10.0,
        status="ok", audio_duration=100,
    ))
    assert s2.avg_speed_mb == pytest.approx(2.0)


def test_display_name_relative(tmp_path):
    base = tmp_path / "books"
    (base / "sub").mkdir(parents=True)
    src = base / "sub" / "ch01.mp3"
    src.touch()
    r = ob.ConversionResult(name="ch01.mp3", source=src, output=src.with_suffix(".opus"),
                            src_bytes=1, opus_bytes=1, duration_s=0, status="ok")
    assert ob._display_name(r, base) == str(Path("sub/ch01.mp3"))
    assert ob._display_name(r, None) == "ch01.mp3"


def test_build_result_table_relative(tmp_path):
    base = tmp_path
    src = base / "sub" / "ch01.mp3"
    src.parent.mkdir(parents=True)
    src.touch()
    s = ob.Stats()
    s.results.append(ob.ConversionResult(
        name="ch01.mp3", source=src, output=src.with_suffix(".opus"),
        src_bytes=1000, opus_bytes=400, duration_s=1.0, status="ok", audio_duration=60))
    table = ob.build_result_table(s, max_rows=30, base_dir=base)
    # renders without error and contains relative path column content
    assert table.row_count == 1


def test_summary_negative_saved():
    s = ob.Stats(elapsed_s=1.0)
    s.results.append(ob.ConversionResult(
        name="a", source=Path("a"), output=Path("b"),
        src_bytes=100, opus_bytes=200, duration_s=1.0, status="ok", audio_duration=10))
    panel = ob.build_summary_panel(s, "64k")
    assert panel is not None


# ── ffprobe parsing ─────────────────────────────────────────────────
def test_get_file_metadata_first_audio_wins():
    payload = {
        "format": {"duration": "123.4"},
        "streams": [
            {"codec_type": "audio", "channels": 1},
            {"codec_type": "audio", "channels": 6},
            {"codec_type": "video"},
        ],
    }
    with patch.object(subprocess, "check_output", return_value=json.dumps(payload)):
        dur, ch, cover = ob.get_file_metadata(Path("x.mp3"), "ffprobe")
    assert dur == pytest.approx(123.4)
    assert ch == 1
    assert cover is True


def test_get_file_metadata_error_returns_zeros():
    with patch.object(subprocess, "check_output", side_effect=RuntimeError("boom")):
        assert ob.get_file_metadata(Path("x.mp3"), "ffprobe") == (0.0, 0, False)


# ── convert_file ────────────────────────────────────────────────────
def test_convert_skipped_when_exists(tmp_path):
    src = tmp_path / "a.mp3"
    src.write_bytes(b"x" * 1000)
    out = tmp_path / "a.opus"
    out.write_bytes(b"y" * 400)
    r = ob.convert_file(src, "64k", force=False, ffmpeg="ffmpeg", ffprobe="ffprobe",
                        duration=10.0, progress=None, inner_task_id=None)
    assert r.status == "skipped"
    assert r.src_bytes == 1000
    assert r.opus_bytes == 400


def test_convert_unreadable_source(tmp_path):
    src = tmp_path / "missing.mp3"
    r = ob.convert_file(src, "64k", force=False, ffmpeg="ffmpeg", ffprobe="ffprobe",
                        duration=5.0, progress=None, inner_task_id=None)
    assert r.status == "failed"
    assert "unreadable" in r.error


def test_convert_failure_unlinks_partial(tmp_path):
    src = tmp_path / "a.mp3"
    src.write_bytes(b"x" * 1000)
    out = src.with_suffix(".opus")
    out.write_bytes(b"partial")

    proc = MagicMock()
    proc.stdout = ["progress=end"]
    proc.wait.return_value = None
    proc.returncode = 1
    proc.stderr = MagicMock()
    proc.stderr.read.return_value = "ffmpeg boom"
    with patch.object(subprocess, "Popen", return_value=proc):
        r = ob.convert_file(src, "64k", force=True, ffmpeg="ffmpeg", ffprobe="ffprobe",
                            duration=10.0, progress=None, inner_task_id=None)
    assert r.status == "failed"
    assert not out.exists(), "partial .opus must be removed on failure"


def test_convert_success_uses_first_audio_stream(tmp_path):
    src = tmp_path / "a.m4b"
    src.write_bytes(b"x" * 2048)

    captured = {}

    class FakeStdout(list):
        pass

    proc = MagicMock()
    proc.stdout = ["out_time_us=1000000", "progress=end"]
    proc.wait.return_value = None
    proc.returncode = 0
    proc.stderr = MagicMock()
    proc.stderr.read.return_value = ""

    def fake_popen(args, **kwargs):
        captured["args"] = args
        # simulate ffmpeg writing output file
        (tmp_path / "a.opus").write_bytes(b"o" * 512)
        return proc

    with patch.object(subprocess, "Popen", side_effect=fake_popen):
        with patch.object(ob, "ffprobe_duration", return_value=60.0):
            with patch.object(ob, "extract_cover", return_value=False):
                r = ob.convert_file(src, "64k", force=True, ffmpeg="ffmpeg",
                                    ffprobe="ffprobe", duration=60.0,
                                    progress=None, inner_task_id=None,
                                    extracted_covers=set(), cover_lock=None)
    assert r.status == "ok"
    assert "-map" in captured["args"]
    idx = captured["args"].index("-map")
    assert captured["args"][idx + 1] == "0:a:0"
    assert r.opus_bytes == 512


# ── CLI validation ──────────────────────────────────────────────────
def test_cli_delete_keep_conflict(tmp_path):
    with pytest.raises(SystemExit) as e:
        ob.main([".", "-b", "64k", "--delete", "--keep"])
    assert e.value.code == 2


def test_cli_invalid_jobs():
    with pytest.raises(SystemExit) as e:
        ob.main([".", "-b", "64k", "-j", "0"])
    assert e.value.code == 2


def test_cli_invalid_max_table():
    with pytest.raises(SystemExit) as e:
        ob.main([".", "-b", "64k", "--max-table", "0"])
    assert e.value.code == 2


def test_cli_version():
    with pytest.raises(SystemExit) as e:
        ob.main(["--version"])
    assert e.value.code == 0


def test_cli_dry_run_no_ffmpeg_needed(tmp_path, monkeypatch):
    # dry-run still requires ffmpeg/ffprobe lookup; mock them + metadata
    d = tmp_path / "book"
    d.mkdir()
    (d / "ch1.mp3").write_bytes(b"x" * 100)
    monkeypatch.setattr(ob, "check_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(ob, "get_ffmpeg_version", lambda p: "test")
    monkeypatch.setattr(ob, "find_ffprobe", lambda: "ffprobe")
    monkeypatch.setattr(ob, "get_file_metadata", lambda p, f: (60.0, 2, False))
    # should complete without raising (prints table + summary)
    ob.main([str(d), "-b", "64k", "--dry-run", "--keep"])
