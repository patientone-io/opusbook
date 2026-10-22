import importlib.util
import os
from pathlib import Path
import sys
import time

import pytest

import opusbook as ob


spec = importlib.util.spec_from_file_location(
    "windows_entry", Path(__file__).resolve().parents[1] / "packaging" / "windows_entry.py",
)
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


def test_frozen_tools_take_priority_over_path(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "opusbook.exe"))
    for name in ("ffmpeg", "ffprobe"):
        (tmp_path / (name + ".exe")).touch()
    monkeypatch.setattr(ob.shutil, "which", lambda name: "unrelated-system-tool")
    assert ob.check_ffmpeg() == str(tmp_path / "ffmpeg.exe")
    assert ob.find_ffprobe() == str(tmp_path / "ffprobe.exe")


def test_linux_frozen_tools_take_priority_over_path(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "opusbook"))
    for name in ("ffmpeg", "ffprobe"):
        (tmp_path / name).touch()
    monkeypatch.setattr(ob.shutil, "which", lambda name: "unrelated-system-tool")
    assert ob.check_ffmpeg() == str(tmp_path / "ffmpeg")
    assert ob.find_ffprobe() == str(tmp_path / "ffprobe")


def test_unfrozen_does_not_trust_adjacent_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    (tmp_path / "ffmpeg.exe").touch()
    monkeypatch.setattr(ob.shutil, "which", lambda name: "system-ffmpeg")
    assert ob.check_ffmpeg() == "system-ffmpeg"


def test_ffprobe_windows_sibling(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ob, "_find_tool", lambda name: str(tmp_path / "ffmpeg.exe") if name == "ffmpeg" else "")
    (tmp_path / "ffprobe.exe").touch()
    (tmp_path / "ffprobe.exe").chmod(0o755)
    assert ob.find_ffprobe() == str(tmp_path / "ffprobe.exe")


def test_dropped_folder_is_recursive_and_keeps_sources(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ob, "main", calls.append)
    assert entry.main([str(tmp_path)]) == 0
    assert calls == [[str(tmp_path.resolve()), "-r", "--keep"]]


def test_wizard_blank_path_cancels(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr(ob, "main", lambda args: pytest.fail("Blank path must not convert CWD"))
    assert entry.main([]) == 0


def test_wizard_accepts_quoted_path(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("builtins.input", lambda prompt: f'"{tmp_path}"')
    monkeypatch.setattr(ob, "main", calls.append)
    assert entry.main([]) == 0
    assert calls == [[str(tmp_path.resolve()), "-r", "--keep"]]


@pytest.mark.parametrize("code", [1, 130])
def test_portable_preserves_failure_exit_code(tmp_path, monkeypatch, code):
    def fail(args):
        raise SystemExit(code)
    monkeypatch.setattr(ob, "main", fail)
    assert entry.main([str(tmp_path)]) == code


def test_explicit_options_use_regular_cli(monkeypatch):
    calls = []
    monkeypatch.setattr(ob, "main", calls.append)
    entry.main(["book", "--delete", "-b", "64k"])
    assert calls == [["book", "--delete", "-b", "64k"]]


def test_windows_language_without_posix_environment(monkeypatch):
    for variable in ("OPUSBOOK_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(ob.locale, "getlocale", lambda: ("Polish_Poland", "1250"))
    assert ob.detect_system_language() == "pl"
    monkeypatch.setenv("OPUSBOOK_LANG", "en")
    assert ob.detect_system_language() == "en"


@pytest.mark.skipif(os.name != "nt", reason="Windows ChangeTime regression")
def test_windows_signature_detects_edit_with_restored_mtime(tmp_path):
    path = tmp_path / "source.wav"
    path.write_bytes(b"original")
    before = path.stat()
    signature = ob._path_signature(path)
    # NTFS timestamps use the system clock; two writes in one clock tick can
    # have identical ChangeTime. Separate the writes to isolate restored mtime.
    time.sleep(0.05)
    path.write_bytes(b"modified")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    changed = ob._path_signature(path)
    assert changed[:4] == signature[:4]
    assert changed[4] != signature[4]


@pytest.mark.skipif(os.name != "nt", reason="Windows content fingerprint regression")
def test_windows_signature_detects_edit_even_when_all_timestamps_match(tmp_path, monkeypatch):
    path = tmp_path / "source.wav"
    path.write_bytes(b"original")
    with path.open("rb") as source:
        metadata = ob._handle_signature(source.fileno())
    monkeypatch.setattr(ob, "_handle_signature", lambda fd: metadata)
    before = ob._path_signature(path)
    path.write_bytes(b"modified")
    after = ob._path_signature(path)
    assert before[:5] == after[:5]
    assert before[5] != after[5]
    with pytest.raises(OSError):
        ob._check_signature(path, before, "source_changed")
