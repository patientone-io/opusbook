"""Unit + integration tests for opusbook (mocked ffmpeg/ffprobe)."""
import json
import errno
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import opusbook as ob
from rich.console import Console


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


def test_get_file_metadata_error_returns_unknown_cover():
    with patch.object(subprocess, "check_output", side_effect=RuntimeError("boom")):
        assert ob.get_file_metadata(Path("x.mp3"), "ffprobe") == (0.0, 0, None)


@pytest.mark.parametrize("stream_duration, expected", [
    ({"duration": "1.25"}, 1.25),
    ({"duration": "N/A", "duration_ts": 60000, "time_base": "1/48000"}, 1.25),
    ({"duration": "nan"}, 123.4),
    ({"duration": "inf"}, 123.4),
    ({"duration": "-5"}, 123.4),
    ({"duration": None, "duration_ts": 42, "time_base": "1/0"}, 123.4),
])
def test_metadata_duration_comes_from_first_audio(stream_duration, expected):
    payload = {
        "format": {"duration": "123.4"},
        "streams": [
            {"codec_type": "audio", "channels": 1, **stream_duration},
            {"codec_type": "audio", "channels": 2, "duration": "123.4"},
        ],
    }
    with patch.object(subprocess, "check_output", return_value=json.dumps(payload)):
        assert ob.get_file_metadata(Path("book.m4b"), "ffprobe") == (expected, 1, False)


def test_metadata_does_not_take_channels_from_second_audio():
    payload = {
        "format": {"duration": "3"},
        "streams": [
            {"codec_type": "audio", "duration": "1"},
            {"codec_type": "audio", "channels": 1, "duration": "3"},
        ],
    }
    with patch.object(subprocess, "check_output", return_value=json.dumps(payload)):
        assert ob.get_file_metadata(Path("book.m4b"), "ffprobe") == (1.0, 0, False)


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
    assert not list(tmp_path.glob(".opusbook.*.opus"))


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
                                    extracted_covers={}, cover_lock=None)
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
    assert not list(tmp_path.glob(".opusbook.*.opus"))


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
    assert not list(tmp_path.glob(".opusbook.*.opus"))


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
    assert not list(tmp_path.glob(".opusbook.*.opus"))


@pytest.fixture
def audio_source(tmp_path, monkeypatch):
    import wave

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg required")
    monkeypatch.setattr(ob, "console", Console(file=io.StringIO(), width=1000))
    source = tmp_path / "voice.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * 48000)
    return source


@pytest.fixture
def covered_source(audio_source):
    image = audio_source.with_name("image.ppm")
    image.write_bytes(b"P6\n32 32\n255\n" + b"\xff\0\0" * 32 * 32)
    source = audio_source.with_suffix(".mp3")
    subprocess.run([
        shutil.which("ffmpeg"), "-v", "error", "-i", str(audio_source), "-i", str(image),
        "-map", "0:a", "-map", "1:v", "-c:a", "libmp3lame", "-c:v", "mjpeg",
        "-disposition:v", "attached_pic", str(source),
    ], check=True, capture_output=True, timeout=20)
    return source


@pytest.mark.parametrize("first_duration, second_duration", [(1, 3), (3, 1)])
def test_cli_converts_first_audio_track_with_different_track_durations(
    audio_source, first_duration, second_duration,
):
    source = audio_source.with_suffix(".m4b")
    subprocess.run([
        shutil.which("ffmpeg"), "-v", "error",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={first_duration}",
        "-f", "lavfi", "-i", f"sine=frequency=880:duration={second_duration}",
        "-map", "0:a", "-map", "1:a", "-c:a", "aac", "-f", "mp4", str(source),
    ], check=True, capture_output=True, timeout=20)
    assert ob.get_file_metadata(source, shutil.which("ffprobe"))[0] == pytest.approx(first_duration)
    ob.main([str(source), "-b", "64k", "--keep"])
    assert source.exists()
    output = source.with_suffix(".opus")
    assert ob.ffprobe_duration(output, shutil.which("ffprobe")) == pytest.approx(first_duration, abs=.03)


@pytest.mark.parametrize("change", ["replace", "modify", "remove"])
def test_cli_keeps_source_changed_after_conversion(audio_source, monkeypatch, change):
    real_convert = ob.convert_file
    replacement = b"new source, never converted"

    def convert_then_change(*args, **kwargs):
        result = real_convert(*args, **kwargs)
        assert result.status == "ok"
        if change == "replace":
            other = audio_source.with_name("replacement.wav")
            other.write_bytes(replacement)
            os.replace(other, audio_source)
        elif change == "modify":
            original_stat = audio_source.stat()
            with audio_source.open("r+b") as source:
                source.write(replacement)
            # Size and mtime alone cannot detect every modification.
            os.utime(audio_source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        else:
            audio_source.unlink()
        return result

    monkeypatch.setattr(ob, "convert_file", convert_then_change)
    with pytest.raises(SystemExit) as error:
        ob.main([str(audio_source), "-b", "64k", "--delete", "--lang", "en"])
    assert error.value.code == 1
    if change != "remove":
        assert audio_source.read_bytes().startswith(replacement)
    assert audio_source.with_suffix(".opus").exists()


def test_source_changed_during_conversion_preserves_existing_output(audio_source, monkeypatch):
    output = audio_source.with_suffix(".opus")
    output.write_bytes(b"previous valid output")
    real_probe = ob.ffprobe_duration

    def probe_then_change(*args):
        duration = real_probe(*args)
        audio_source.write_bytes(b"changed during conversion")
        return duration

    monkeypatch.setattr(ob, "ffprobe_duration", probe_then_change)
    result = ob.convert_file(audio_source, "64k", True, shutil.which("ffmpeg"),
                             shutil.which("ffprobe"), 1.0)
    assert result.status == "failed"
    assert output.read_bytes() == b"previous valid output"
    assert not list(audio_source.parent.glob(".opusbook.*.opus"))


@pytest.mark.parametrize("previous_cover", [None, b"", b"not an image"])
def test_cli_repairs_invalid_cover_before_deleting_source(covered_source, previous_cover):
    cover = covered_source.with_name("cover.jpg")
    if previous_cover is not None:
        cover.write_bytes(previous_cover)
    ob.main([str(covered_source), "-b", "64k", "--delete"])
    assert not covered_source.exists()
    assert cover.read_bytes().startswith(b"\xff\xd8")
    # Decode the image rather than trusting its extension or JPEG header.
    subprocess.run([
        shutil.which("ffmpeg"), "-v", "error", "-xerror", "-i", str(cover),
        "-frames:v", "1", "-f", "null", "-",
    ], check=True, capture_output=True, timeout=20)
    assert not list(cover.parent.glob(".cover.*.jpg"))


@pytest.mark.parametrize("force", [False, True])
def test_failed_cover_export_preserves_source_and_previous_output(covered_source, monkeypatch, force):
    output = covered_source.with_suffix(".opus")
    if force:
        output.write_bytes(b"previous valid output")
    monkeypatch.setattr(ob, "extract_cover", lambda *args: False)
    with pytest.raises(SystemExit) as error:
        ob.main([str(covered_source), "-b", "64k", "--delete"] + (["--force"] if force else []))
    assert error.value.code == 1
    assert covered_source.exists()
    if force:
        assert output.read_bytes() == b"previous valid output"
    else:
        assert not output.exists()
    assert not list(covered_source.parent.glob(".opusbook.*.opus"))


def test_metadata_timeout_keeps_covered_source(covered_source, monkeypatch):
    real_check_output = subprocess.check_output

    def timeout_metadata(args, **kwargs):
        if "-print_format" in args:
            raise subprocess.TimeoutExpired(args, 10)
        return real_check_output(args, **kwargs)

    monkeypatch.setattr(subprocess, "check_output", timeout_metadata)
    with pytest.raises(SystemExit) as error:
        ob.main([str(covered_source), "-b", "64k", "--delete"])
    assert error.value.code == 1
    assert covered_source.exists()
    assert not covered_source.with_suffix(".opus").exists()


def test_valid_existing_cover_is_preserved(covered_source, monkeypatch):
    cover = covered_source.with_name("cover.jpg")
    assert ob.extract_cover(covered_source, cover, shutil.which("ffmpeg"))
    original = cover.read_bytes()
    with patch.object(ob, "extract_cover") as extract:
        ob.main([str(covered_source), "-b", "64k", "--delete"])
    extract.assert_not_called()
    assert cover.read_bytes() == original


@pytest.mark.parametrize("failure", ["encoder", "timeout", "invalid_image"])
def test_failed_cover_extraction_keeps_existing_sidecar(audio_source, monkeypatch, failure):
    cover = audio_source.with_name("cover.jpg")
    cover.write_bytes(b"previous sidecar")
    real_run = subprocess.run

    def fail_extraction(args, **kwargs):
        if args[-1].endswith(".jpg"):
            Path(args[-1]).write_bytes(b"partial image")
            if failure == "timeout":
                raise subprocess.TimeoutExpired(args, 30)
            return subprocess.CompletedProcess(args, 0 if failure == "invalid_image" else 1)
        return real_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_extraction)
    assert not ob.extract_cover(audio_source, cover, shutil.which("ffmpeg"))
    assert cover.read_bytes() == b"previous sidecar"
    assert not list(cover.parent.glob(".cover.*.jpg"))


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions required")
def test_fallback_publication_keeps_private_permissions(tmp_path):
    temporary = tmp_path / "temporary.opus"
    output = tmp_path / "chapter.opus"
    temporary.write_bytes(b"private audio")
    temporary.chmod(0o600)
    previous_umask = os.umask(0o022)
    try:
        with patch.object(ob.os, "link", side_effect=OSError(errno.EOPNOTSUPP, "unsupported")):
            ob._publish_output(temporary, output, force=False)
    finally:
        os.umask(previous_umask)
    assert output.stat().st_mode & 0o777 == 0o600
    assert output.read_bytes() == b"private audio"


@pytest.mark.parametrize("mode", ["convert", "dry-run", "failure", "missing"])
def test_cli_treats_markup_in_paths_as_literal_text(audio_source, mode):
    directory = audio_source.parent / "book [bold]name[" / "red]"
    directory.mkdir(parents=True)
    source = directory / "voice [red].wav"
    audio_source.rename(source)
    if mode == "failure":
        source.write_bytes(b"invalid audio")
    elif mode == "missing":
        source.unlink()
    args = [str(source), "-b", "64k", "--keep", "--lang", "en"]
    if mode == "dry-run":
        args.append("--dry-run")
    if mode in ("failure", "missing"):
        with pytest.raises(SystemExit) as error:
            ob.main(args)
        assert error.value.code == 1
    else:
        ob.main(args)
    assert str(source) in ob.console.file.getvalue()


def test_invalid_bitrate_markup_is_reported_literally(monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(ob, "console", Console(file=output, width=1000))
    with pytest.raises(SystemExit) as error:
        ob.main(["-b", "[/red]", "--lang", "en"])
    assert error.value.code == 1
    assert "Invalid bitrate: '[/red]'." in output.getvalue()


@pytest.mark.parametrize("change", ["remove", "replace", "modify"])
@pytest.mark.parametrize("publication", ["link", "copy", "replace"])
def test_cli_keeps_source_when_output_changes_before_deletion(audio_source, monkeypatch, change, publication):
    real_convert = ob.convert_file
    original_source = audio_source.read_bytes()

    def convert_then_change(*args, **kwargs):
        result = real_convert(*args, **kwargs)
        assert result.status == "ok"
        if change == "remove":
            result.output.unlink()
        elif change == "replace":
            # Even a valid, byte-for-byte copy is a different file.
            replacement = result.output.with_name("replacement.opus")
            replacement.write_bytes(result.output.read_bytes())
            os.replace(replacement, result.output)
        else:
            original_stat = result.output.stat()
            with result.output.open("r+b") as output:
                output.write(b"broken")
            os.utime(result.output, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        return result

    monkeypatch.setattr(ob, "convert_file", convert_then_change)
    if publication == "copy":
        monkeypatch.setattr(ob.os, "link", MagicMock(side_effect=OSError(errno.EOPNOTSUPP, "unsupported")))
    with pytest.raises(SystemExit) as error:
        ob.main([str(audio_source), "-b", "64k", "--delete", "--lang", "en"]
                + (["--force"] if publication == "replace" else []))
    assert error.value.code == 1
    assert audio_source.read_bytes() == original_source


def test_publication_detects_replacement_before_recording_identity(tmp_path, monkeypatch):
    temporary = tmp_path / "temporary.opus"
    output = tmp_path / "voice.opus"
    temporary.write_bytes(b"encoded audio")
    real_link = os.link

    def link_then_replace(source, target):
        real_link(source, target)
        output.unlink()
        output.write_bytes(b"encoded audio")

    monkeypatch.setattr(ob.os, "link", link_then_replace)
    with pytest.raises(OSError):
        ob._publish_output(temporary, output, force=False)


@pytest.mark.parametrize("stem", ["a" * 241, "ą" * 120 + "a"])
def test_cli_converts_long_basenames(audio_source, stem):
    source = audio_source.with_name(stem + ".wav")
    audio_source.rename(source)
    ob.main([str(source), "-b", "64k", "--keep"])
    assert source.exists()
    assert ob.ffprobe_duration(source.with_suffix(".opus"), shutil.which("ffprobe")) == pytest.approx(1, abs=.02)
    assert not list(source.parent.glob(".*.opus"))


@pytest.mark.parametrize("duration", [.001, .01, .05, .1])
def test_cli_converts_short_audio_without_losing_samples(audio_source, duration):
    import wave

    samples = round(48000 * duration)
    with wave.open(str(audio_source), "wb") as audio:
        audio.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * samples)
    ob.main([str(audio_source), "-b", "64k", "--delete"])
    assert not audio_source.exists()
    decoded = subprocess.run([
        shutil.which("ffmpeg"), "-v", "error", "-i", str(audio_source.with_suffix(".opus")),
        "-f", "s16le", "-ar", "48000", "-ac", "1", "-",
    ], check=True, capture_output=True, timeout=20)
    assert len(decoded.stdout) == samples * 2


@pytest.mark.parametrize("source_duration, output_duration", [(.01, .005), (60, 50), (60, 70)])
def test_duration_validation_still_rejects_truncated_or_extended_audio(
    audio_source, monkeypatch, source_duration, output_duration,
):
    monkeypatch.setattr(ob, "ffprobe_duration", lambda *args: output_duration)
    result = ob.convert_file(audio_source, "64k", False, shutil.which("ffmpeg"),
                             shutil.which("ffprobe"), source_duration)
    assert result.status == "failed"
    assert audio_source.exists()
    assert not audio_source.with_suffix(".opus").exists()
    assert not list(audio_source.parent.glob(".*.opus"))


@pytest.fixture
def uncovered_source(covered_source):
    source = covered_source.with_name("plain.mp3")
    subprocess.run([
        shutil.which("ffmpeg"), "-v", "error", "-i", str(covered_source),
        "-map", "0:a:0", "-c:a", "copy", str(source),
    ], check=True, capture_output=True, timeout=20)
    return source


@pytest.mark.parametrize("stage", ["during_probe", "queued"])
@pytest.mark.parametrize("change", ["replace", "modify", "remove"])
@pytest.mark.parametrize("force", [False, True])
def test_cli_rejects_sources_changed_before_encoding(
    uncovered_source, covered_source, monkeypatch, stage, change, force,
):
    replacement = covered_source.read_bytes()
    output = uncovered_source.with_suffix(".opus")
    if force:
        output.write_bytes(b"previous output")

    def change_source():
        if change == "replace":
            other = uncovered_source.with_name("replacement.tmp")
            other.write_bytes(replacement)
            os.replace(other, uncovered_source)
        elif change == "modify":
            uncovered_source.write_bytes(replacement)
        else:
            uncovered_source.unlink()

    if stage == "during_probe":
        real_probe = ob.get_file_metadata

        def probe_then_change(*args, **kwargs):
            metadata = real_probe(*args, **kwargs)
            change_source()
            return metadata

        monkeypatch.setattr(ob, "get_file_metadata", probe_then_change)
    else:
        real_probe = ob._probe_file

        def queue_then_change(*args, **kwargs):
            info = real_probe(*args, **kwargs)
            change_source()
            return info

        monkeypatch.setattr(ob, "_probe_file", queue_then_change)
    with pytest.raises(SystemExit) as error:
        ob.main([str(uncovered_source), "-b", "64k", "--delete"] + (["--force"] if force else []))
    assert error.value.code == 1
    if change != "remove":
        assert uncovered_source.read_bytes() == replacement
    if force:
        assert output.read_bytes() == b"previous output"
    else:
        assert not output.exists()
    assert not list(uncovered_source.parent.glob(".opusbook.*.opus"))


def test_retry_after_source_change_exports_cover(uncovered_source, covered_source, monkeypatch):
    real_probe = ob.get_file_metadata
    original = covered_source.read_bytes()

    def probe_then_replace(*args):
        metadata = real_probe(*args)
        uncovered_source.write_bytes(original)
        return metadata

    with monkeypatch.context() as local:
        local.setattr(ob, "get_file_metadata", probe_then_replace)
        with pytest.raises(SystemExit) as error:
            ob.main([str(uncovered_source), "-b", "64k", "--delete"])
        assert error.value.code == 1
    ob.main([str(uncovered_source), "-b", "64k", "--delete"])
    assert not uncovered_source.exists()
    assert ob._valid_cover(uncovered_source.with_name("cover.jpg"), shutil.which("ffmpeg"))
    assert uncovered_source.with_suffix(".opus").exists()


@pytest.fixture
def hardlinked_sources(audio_source):
    nested = audio_source.parent / "sub"
    nested.mkdir()
    sources = [audio_source, audio_source.with_name("second.wav"), nested / "voice.wav"]
    try:
        for alias in sources[1:]:
            os.link(audio_source, alias)
    except OSError:
        pytest.skip("Filesystem with hardlinks required")
    return sources


@pytest.mark.parametrize("jobs", [1, 4])
@pytest.mark.parametrize("force", [False, True])
def test_cli_deletes_all_converted_hardlink_names(hardlinked_sources, jobs, force):
    if force:
        for source in hardlinked_sources:
            source.with_suffix(".opus").write_bytes(b"previous output")
    ob.main([str(hardlinked_sources[0].parent), "-r", "-b", "64k", "-j", str(jobs), "--delete"]
            + (["--force"] if force else []))
    assert not any(source.exists() for source in hardlinked_sources)
    for source in hardlinked_sources:
        assert ob.ffprobe_duration(source.with_suffix(".opus"), shutil.which("ffprobe")) > 0


def test_hardlink_deletion_does_not_hide_external_content_change(hardlinked_sources, monkeypatch):
    real_unlink = Path.unlink
    original = hardlinked_sources[0].read_bytes()
    changed = original[:512] + b"modified" + original[520:]
    modified = False

    def unlink_then_modify(path, *args, **kwargs):
        nonlocal modified
        result = real_unlink(path, *args, **kwargs)
        if path in hardlinked_sources and not modified:
            modified = True
            remaining = next(source for source in hardlinked_sources if source.exists())
            before = remaining.stat()
            remaining.write_bytes(changed)
            os.utime(remaining, ns=(before.st_atime_ns, before.st_mtime_ns))
        return result

    monkeypatch.setattr(Path, "unlink", unlink_then_modify)
    with pytest.raises(SystemExit) as error:
        ob.main([str(hardlinked_sources[0].parent), "-r", "-b", "64k", "--delete"])
    assert error.value.code == 1
    remaining = [source for source in hardlinked_sources if source.exists()]
    assert len(remaining) == 2
    assert all(source.read_bytes() == changed for source in remaining)


def test_failed_unlink_keeps_hardlink_without_blocking_other_names(hardlinked_sources, monkeypatch):
    real_unlink = Path.unlink
    protected = hardlinked_sources[1]

    def unlink_except_protected(path, *args, **kwargs):
        if path == protected:
            raise PermissionError("cannot unlink source")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink_except_protected)
    with pytest.raises(SystemExit) as error:
        ob.main([str(hardlinked_sources[0].parent), "-r", "-b", "64k", "--delete"])
    assert error.value.code == 1
    assert [source for source in hardlinked_sources if source.exists()] == [protected]


@pytest.mark.parametrize("change", ["remove", "corrupt", "replace"])
def test_cli_keeps_source_when_cover_changes_before_deletion(covered_source, monkeypatch, change):
    real_convert = ob.convert_file
    original = covered_source.read_bytes()

    def convert_then_change(*args, **kwargs):
        result = real_convert(*args, **kwargs)
        assert result.status == "ok"
        cover = result.cover_path
        assert cover is not None
        if change == "remove":
            cover.unlink()
        elif change == "corrupt":
            cover.write_bytes(b"invalid cover")
        else:
            replacement = cover.with_name("replacement.jpg")
            replacement.write_bytes(cover.read_bytes())
            os.replace(replacement, cover)
        return result

    monkeypatch.setattr(ob, "convert_file", convert_then_change)
    with pytest.raises(SystemExit) as error:
        ob.main([str(covered_source), "-b", "64k", "--delete"])
    assert error.value.code == 1
    assert covered_source.read_bytes() == original
    assert covered_source.with_suffix(".opus").exists()


@pytest.mark.parametrize("change", ["remove", "corrupt"])
def test_cover_cache_revalidates_changed_files(covered_source, change):
    other = covered_source.with_name("other.mp3")
    other.write_bytes(covered_source.read_bytes())
    cache = {}
    kwargs = dict(bitrate="64k", force=False, ffmpeg=shutil.which("ffmpeg"),
                  ffprobe=shutil.which("ffprobe"), duration=1.0, has_cover=True, extracted_covers=cache)
    first = ob.convert_file(covered_source, **kwargs)
    assert first.status == "ok"
    cover = covered_source.with_name("cover.jpg")
    if change == "remove":
        cover.unlink()
    else:
        cover.write_bytes(b"invalid image")
    second = ob.convert_file(other, **kwargs)
    assert second.status == "ok"
    assert ob._valid_cover(cover, shutil.which("ffmpeg"))


def test_metadata_failure_is_reported_in_dry_run(audio_source, monkeypatch):
    monkeypatch.setattr(ob, "get_file_metadata", lambda *args: (0.0, 0, None))
    with pytest.raises(SystemExit) as error:
        ob.main([str(audio_source), "-b", "64k", "--dry-run", "--keep"])
    assert error.value.code == 1
    assert audio_source.exists()
    assert not audio_source.with_suffix(".opus").exists()


@pytest.mark.parametrize("force", [False, True])
def test_source_changed_during_cover_export_is_preserved(covered_source, monkeypatch, force):
    real_extract = ob.extract_cover
    output = covered_source.with_suffix(".opus")
    if force:
        output.write_bytes(b"previous valid output")
    replacement = b"source replaced while exporting cover"

    def extract_then_replace(*args, **kwargs):
        success = real_extract(*args, **kwargs)
        assert success
        covered_source.write_bytes(replacement)
        return success

    monkeypatch.setattr(ob, "extract_cover", extract_then_replace)
    with pytest.raises(SystemExit) as error:
        ob.main([str(covered_source), "-b", "64k", "--delete"] + (["--force"] if force else []))
    assert error.value.code == 1
    assert covered_source.read_bytes() == replacement
    if force:
        assert output.read_bytes() == b"previous valid output"
    else:
        assert not output.exists()


def test_metadata_without_audio_is_not_treated_as_absent_cover():
    payload = {"format": {"duration": "1"}, "streams": [{"codec_type": "video"}]}
    with patch.object(subprocess, "check_output", return_value=json.dumps(payload)):
        assert ob.get_file_metadata(Path("book.mp3"), "ffprobe") == (1.0, 0, None)


def test_parallel_hardlinks_export_covers_in_each_directory(covered_source):
    first_dir = covered_source.parent / "book1"
    second_dir = covered_source.parent / "book2"
    first_dir.mkdir()
    second_dir.mkdir()
    sources = [first_dir / "part1.mp3", first_dir / "part2.mp3", second_dir / "part1.mp3"]
    covered_source.rename(sources[0])
    for source in sources[1:]:
        os.link(sources[0], source)
    # Run the full CLI in a separate process, without mocks.
    completed = subprocess.run([
        sys.executable, str(Path(ob.__file__)), str(covered_source.parent),
        "-r", "-b", "64k", "--auto", "-j", "4", "--delete",
    ], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not any(source.exists() for source in sources)
    for source in sources:
        assert ob.ffprobe_duration(source.with_suffix(".opus"), shutil.which("ffprobe")) > 0
    for directory in (first_dir, second_dir):
        assert ob._valid_cover(directory / "cover.jpg", shutil.which("ffmpeg"))


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions required")
def test_delete_with_covers_and_copy_fallback_keeps_private_permissions(covered_source, monkeypatch):
    covered_source.chmod(0o600)
    monkeypatch.setattr(ob.os, "link", MagicMock(side_effect=OSError(errno.EOPNOTSUPP, "unsupported")))
    ob.main([str(covered_source), "-b", "64k", "--delete"])
    assert not covered_source.exists()
    assert covered_source.with_suffix(".opus").stat().st_mode & 0o777 == 0o600
    assert covered_source.with_name("cover.jpg").stat().st_mode & 0o777 == 0o600
