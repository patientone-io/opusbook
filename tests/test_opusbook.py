"""Unit + integration tests for opusbook (mocked ffmpeg/ffprobe)."""
import json
import errno
import shutil
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


def test_convert_failure_preserves_existing_output(tmp_path):
    src = tmp_path / "a.mp3"
    src.write_bytes(b"x" * 1000)
    out = src.with_suffix(".opus")
    out.write_bytes(b"previous valid output")

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
    assert out.read_bytes() == b"previous valid output"
    assert not list(tmp_path.glob(".a.*.opus"))


@pytest.mark.parametrize("chmod_error", [False, True])
def test_convert_success_uses_first_audio_stream(tmp_path, monkeypatch, chmod_error):
    src = tmp_path / "a.m4b"
    src.write_bytes(b"x" * 2048)

    if chmod_error:
        def unsupported_chmod(self, mode):
            raise OSError(errno.EPERM, "Operation not permitted")

        monkeypatch.setattr(Path, "chmod", unsupported_chmod)

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
        Path(args[-1]).write_bytes(b"o" * 512)
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
    assert (tmp_path / "a.opus").read_bytes() == b"o" * 512


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


@pytest.mark.parametrize("duration", [0.0, 60.0])
def test_convert_rejects_missing_output(tmp_path, duration):
    src = tmp_path / "empty.mp3"
    src.write_bytes(b"source")
    proc = MagicMock(returncode=0, stdout=[])
    proc.stderr.read.return_value = ""
    with patch.object(subprocess, "Popen", return_value=proc):
        with patch.object(ob, "ffprobe_duration", return_value=0.0):
            result = ob.convert_file(src, "64k", False, "ffmpeg", "ffprobe", duration)
    assert result.status == "failed"
    assert src.exists()
    assert not src.with_suffix(".opus").exists()
    assert not list(tmp_path.glob(".empty.*.opus"))


@pytest.mark.parametrize("force", [False, True])
def test_cli_rejects_output_collisions_before_probing(tmp_path, monkeypatch, force):
    for suffix in (".mp3", ".m4b"):
        (tmp_path / f"chapter{suffix}").write_bytes(b"source")
    monkeypatch.setattr(ob, "check_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(ob, "get_ffmpeg_version", lambda p: "test")
    monkeypatch.setattr(ob, "find_ffprobe", lambda: "ffprobe")
    with patch.object(ob, "get_file_metadata") as probe:
        with pytest.raises(SystemExit) as error:
            ob.main([str(tmp_path), "-b", "64k", "--delete"] + (["--force"] if force else []))
    assert error.value.code == 1
    probe.assert_not_called()
    assert len(list(tmp_path.iterdir())) == 2


@pytest.mark.parametrize("fallback", [False, True])
def test_publish_does_not_overwrite_racing_output(tmp_path, fallback):
    temporary = tmp_path / "temporary.opus"
    output = tmp_path / "chapter.opus"
    temporary.write_bytes(b"new")
    output.write_bytes(b"existing")
    with patch.object(ob.os, "link", side_effect=OSError(errno.EOPNOTSUPP, "unsupported")) if fallback else patch.object(ob.os, "link", wraps=ob.os.link):
        with pytest.raises(FileExistsError):
            ob._publish_output(temporary, output, force=False)
    assert output.read_bytes() == b"existing"


def test_publish_without_hardlink_support(tmp_path):
    temporary = tmp_path / "temporary.opus"
    output = tmp_path / "chapter.opus"
    temporary.write_bytes(b"new audio")
    with patch.object(ob.os, "link", side_effect=OSError(errno.EOPNOTSUPP, "unsupported")):
        ob._publish_output(temporary, output, force=False)
    assert output.read_bytes() == b"new audio"
    assert not temporary.exists()


@pytest.mark.parametrize("invalid", ["nan", "inf", "-5"])
def test_probe_rejects_invalid_duration(invalid):
    with patch.object(subprocess, "check_output", return_value=invalid):
        assert ob.ffprobe_duration(Path("audio.opus"), "ffprobe") == 0.0
    payload = {"format": {"duration": invalid}, "streams": []}
    with patch.object(subprocess, "check_output", return_value=json.dumps(payload)):
        assert ob.get_file_metadata(Path("audio.mp3"), "ffprobe")[0] == 0.0


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_real_cli_conversion_and_failed_force_preserves_audio(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    source = tmp_path / "voice.wav"
    subprocess.run([
        ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        str(source),
    ], check=True, capture_output=True)
    cli = [sys.executable, str(Path(ob.__file__)), str(source), "-b", "64k", "--lang", "en"]
    completed = subprocess.run(cli + ["--keep"], capture_output=True, text=True, timeout=20)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    output = source.with_suffix(".opus")
    original_output = output.read_bytes()
    assert ob.ffprobe_duration(output, shutil.which("ffprobe")) == pytest.approx(1, abs=0.05)

    source.write_bytes(b"corrupted source")
    failed = subprocess.run(cli + ["--force", "--delete"], capture_output=True, text=True, timeout=20)
    assert failed.returncode == 1, failed.stdout + failed.stderr
    assert source.read_bytes() == b"corrupted source"
    assert output.read_bytes() == original_output
    assert not list(tmp_path.glob(".voice.*.opus"))


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_real_cli_delete_after_success(tmp_path):
    import wave

    source = tmp_path / "voice.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * 48000)
    completed = subprocess.run([
        sys.executable, str(Path(ob.__file__)), str(source), "-b", "64k", "--delete",
    ], capture_output=True, text=True, timeout=20)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not source.exists()
    assert source.with_suffix(".opus").stat().st_size > 0


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_cancellation_stops_running_ffmpeg_and_preserves_output(tmp_path):
    import threading
    import wave

    source = tmp_path / "voice.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * 48000 * 3)
    output = source.with_suffix(".opus")
    output.write_bytes(b"existing audio")
    cancelled = threading.Event()
    real_popen = subprocess.Popen
    processes = []
    timers = []

    def start_realtime(args, **kwargs):
        args.insert(args.index("-i"), "-re")
        process = real_popen(args, **kwargs)
        processes.append(process)
        timer = threading.Timer(0.2, cancelled.set)
        timer.start()
        timers.append(timer)
        return process

    with patch.object(subprocess, "Popen", side_effect=start_realtime):
        result = ob.convert_file(source, "64k", True, shutil.which("ffmpeg"),
                                 shutil.which("ffprobe"), 3.0, cancel_event=cancelled)
    for timer in timers:
        timer.join()
    assert result.status == "failed"
    assert processes[0].poll() is not None
    assert output.read_bytes() == b"existing audio"
    assert source.exists()
    assert not list(tmp_path.glob(".voice.*.opus"))
