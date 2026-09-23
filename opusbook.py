#!/usr/bin/env python3
"""
opusbook.py — Multi-format audio to Opus converter / Konwerter audio do formatu Opus
Usage / Użycie: opusbook [path/ścieżka] [options/opcje]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

__version__ = "1.2.0"

# ── Sprawdzenie zależności / Dependency check ───────────────────────────────
try:
    from rich import box
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table
    from rich.text import Text
    from rich.prompt import Prompt
except ImportError:
    lang = "pl" if os.environ.get("LANG", "").lower().startswith("pl") else "en"
    if lang == "pl":
        print(
            "\n[BŁĄD] Wymagana biblioteka 'rich' nie jest zainstalowana.\n"
            "Zainstaluj ją: pip install rich\n"
        )
    else:
        print(
            "\n[ERROR] Required library 'rich' is not installed.\n"
            "Install it: pip install rich\n"
        )
    sys.exit(1)

console = Console()

SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".m4b", ".m4a", ".flac", ".aac", ".wav", ".ogg", ".wma"}

# ── Internacjonalizacja (i18n) / Localization ──────────────────────────────

MESSAGES = {
    "en": {
        "missing_ffmpeg_title": "Missing dependency",
        "missing_ffmpeg_body": (
            "[bold red]❌ ffmpeg not found![/]\n\n"
            "Please install ffmpeg:\n"
            "  [cyan]• Linux:[/]   sudo apt install ffmpeg (or pacman -S ffmpeg)\n"
            "  [cyan]• Windows:[/] winget install ffmpeg\n"
            "  [cyan]• macOS:[/]   brew install ffmpeg"
        ),
        "missing_ffprobe_title": "Missing dependency",
        "missing_ffprobe_body": (
            "[bold red]❌ ffprobe not found![/]\n\n"
            "ffprobe is required for audio duration and channel inspection.\n"
            "Please install ffmpeg package:\n"
            "  [cyan]• Linux:[/]   sudo apt install ffmpeg\n"
            "  [cyan]• Windows:[/] winget install ffmpeg\n"
            "  [cyan]• macOS:[/]   brew install ffmpeg"
        ),
        "nav_hint": "[dim](↑/↓ navigate, 1/2/3 jump, Enter select, Ctrl+C abort)[/]",
        "fallback_prompt_suffix": " [dim](1-{count} or full value)[/]",
        "bitrate_prompt": "Select target Opus bitrate",
        "bitrate_48k": "speech only (voice without music)",
        "bitrate_64k": "speech + music (default, audio plays)",
        "bitrate_80k": "full production (music + sound effects)",
        "invalid_bitrate": "[red]Invalid bitrate: {bitrate!r}. Use e.g. 48k, 64k, 128k, 1M.[/]",
        "bitrate_low_warn": "[yellow]⚠ Bitrate < 32k — quality may be degraded for music[/]",
        "bitrate_high_warn": "[yellow]⚠ Bitrate > 256k — overkill for speech[/]",
        "path_not_found": "[red]Path does not exist: {path}[/]",
        "scanning_files": "[cyan]Scanning audio files…[/]",
        "no_audio_files": "[yellow]No supported audio files ({exts}) found in:[/]\n[white]{path}[/]",
        "probing_metadata": "[cyan]Extracting metadata (ffprobe)…[/]",
        "probing_status": "[cyan]Metadata… {i}/{total} · {name}[/]",
        "header_title": "[bold cyan]🎵 opusbook[/]  [dim]Audio → Opus converter[/]",
        "header_dir": "Directory:",
        "header_bitrate": "Bitrate:",
        "header_jobs": "Workers:",
        "header_auto": "Auto:",
        "header_recurse": "Recursive:",
        "header_force": "Force:",
        "header_files": "Files:",
        "yes": "yes",
        "no": "no",
        "with_cover": "with cover",
        "progress_all": "[bold]Overall[/]",
        "progress_left": "[dim]· left[/]",
        "table_title": "Conversion Results",
        "col_file": "File",
        "col_source": "Source",
        "col_opus": "Opus",
        "col_saved": "Saved",
        "col_ratio": "Reduction",
        "col_audio_time": "Audio Time",
        "col_conv_time": "Conv. Time",
        "col_status": "Status",
        "table_caption": "Showing last {max_rows} of {total} files",
        "status_skipped": "[dim]⏩ skipped[/]",
        "status_failed": "[bold red]✗ error[/]",
        "summary_title": "[bold cyan]📊 Summary[/]",
        "summary_converted": "  [bold white]Converted:[/]     [green bold]{count}[/] files ({duration} audio)",
        "summary_skipped": "  [bold white]Skipped:[/]       [dim]{count}[/] files",
        "summary_failed": "  [bold white]Errors:[/]        {count}",
        "summary_source": "  [bold white]Source size:[/]   [yellow]{size}[/]",
        "summary_opus": "  [bold white]Opus size:[/]     [cyan]{size}[/]",
        "summary_saved_ok": "  [bold white]Saved space:[/]   [green bold]{size}[/]",
        "summary_saved_neg": "  [bold white]Saved space:[/]   [red bold]{size} (output larger!)[/]",
        "summary_speed": "  [bold white]Speed:[/]         [dim]{speed:.1f} MB/s[/]",
        "summary_bitrate": "  [bold white]Bitrate:[/]       [cyan]{bitrate}[/]  [dim](64k — speech+music, 48k — voice only, 80k — full production)[/]",
        "summary_failed_hdr": "  [red bold]Failed files:[/]",
        "delete_prompt": "[yellow]Delete original audio files? [y/N][/]",
        "delete_choices": ["y", "n"],
        "delete_default": "n",
        "delete_confirm_val": "y",
        "deleting_status": "[red]Deleting original audio files…[/]",
        "delete_error": "[red]  Error deleting {name}: {err}[/]",
        "deleted_success": "  [green]✅ Deleted {count} source files.[/]",
        "deleted_errors": " [red]({count} errors)[/]",
        "delete_kept": "  [dim]Original files kept.[/]",
        "cli_desc": "Multi-format audio to Opus converter | Cross-platform",
        "cli_epilog": (
            "Examples:\n"
            "  opusbook .                     # convert current directory with default 64k\n"
            "  opusbook audiobooks/ -r        # recursive search\n"
            "  opusbook radio_play/ -b 80k    # full production (music + SFX)\n"
            "  opusbook narration/ -b 48k     # speech only, no music\n"
            "  opusbook . --delete            # convert and auto-remove source files"
        ),
        "cli_path_metavar": "PATH",
        "cli_path_help": "Directory containing audio files (default: current directory)",
        "cli_bitrate_help": "Opus bitrate — 64k default (speech+music), 48k (narration), 80k (full production)",
        "cli_jobs_help": "Number of concurrent conversion workers (default: min(4, CPU cores))",
        "cli_recurse_help": "Search subdirectories recursively",
        "cli_auto_help": "Auto-bitrate: mono→32k, stereo→from -b (default 64k)",
        "cli_force_help": "Overwrite existing .opus files",
        "cli_keep_help": "Keep source files without interactive confirmation",
        "cli_delete_help": "Delete source files without confirmation (non-interactive)",
        "cli_max_table_help": "Max rows in results table (default: 30)",
        "cli_dry_run_help": "Preview scheduled ffmpeg commands without executing",
        "cli_lang_help": "Interface language (auto, en, pl)",
        "non_tty_bitrate": "[dim]No TTY detected — using default bitrate 64k (pass -b to override).[/]",
        "aborted": "[red]Aborted by user (Ctrl+C). Waiting for workers to stop…[/]",
        "invalid_jobs": "[red]Invalid --jobs value: {value!r}. Use an integer >= 1.[/]",
        "invalid_max_table": "[red]Invalid --max-table value: {value!r}. Use an integer >= 1.[/]",
        "delete_keep_conflict": "[red]Options --delete and --keep are mutually exclusive.[/]",
        "unsupported_file": "[red]Unsupported audio format: {path}[/]",
        "stat_error": "[yellow]Skipping unreadable file: {path}[/]",
        "dry_run_header": "[bold cyan]DRY-RUN — planned ffmpeg commands:[/]",
    },
    "pl": {
        "missing_ffmpeg_title": "Brak zależności",
        "missing_ffmpeg_body": (
            "[bold red]❌ Nie znaleziono ffmpeg![/]\n\n"
            "Zainstaluj go:\n"
            "  [cyan]• Linux:[/]   sudo apt install ffmpeg (lub pacman -S ffmpeg)\n"
            "  [cyan]• Windows:[/] winget install ffmpeg\n"
            "  [cyan]• macOS:[/]   brew install ffmpeg"
        ),
        "missing_ffprobe_title": "Brak zależności",
        "missing_ffprobe_body": (
            "[bold red]❌ Nie znaleziono ffprobe![/]\n\n"
            "ffprobe jest wymagany do pobierania metadanych (czas trwania, kanały, okładki).\n"
            "Zainstaluj go:\n"
            "  [cyan]• Linux:[/]   sudo apt install ffmpeg\n"
            "  [cyan]• Windows:[/] winget install ffmpeg\n"
            "  [cyan]• macOS:[/]   brew install ffmpeg"
        ),
        "nav_hint": "[dim](↑/↓ nawigacja, 1/2/3 skok, Enter wybór, Ctrl+C przerwij)[/]",
        "fallback_prompt_suffix": " [dim](1-{count} lub pełna wartość)[/]",
        "bitrate_prompt": "Wybierz jakość bitrate dla plików Opus",
        "bitrate_48k": "sama narracja (lektor bez muzyki)",
        "bitrate_64k": "mowa + muzyka (domyślne, słuchowiska)",
        "bitrate_80k": "pełna produkcja (muzyka + efekty)",
        "invalid_bitrate": "[red]Błędny bitrate: {bitrate!r}. Użyj np. 48k, 64k, 128k, 1M.[/]",
        "bitrate_low_warn": "[yellow]⚠ Bitrate < 32k — jakość może być słaba dla muzyki[/]",
        "bitrate_high_warn": "[yellow]⚠ Bitrate > 256k — przepłacanie dla mowy[/]",
        "path_not_found": "[red]Ścieżka nie istnieje: {path}[/]",
        "scanning_files": "[cyan]Skanowanie plików audio…[/]",
        "no_audio_files": "[yellow]Brak wspieranych plików audio ({exts}) w katalogu:[/]\n[white]{path}[/]",
        "probing_metadata": "[cyan]Pobieranie metadanych (ffprobe)…[/]",
        "probing_status": "[cyan]Metadane… {i}/{total} · {name}[/]",
        "header_title": "[bold cyan]🎵 opusbook[/]  [dim]Konwerter audio → Opus[/]",
        "header_dir": "Katalog:",
        "header_bitrate": "Bitrate:",
        "header_jobs": "Wątki:",
        "header_auto": "Auto:",
        "header_recurse": "Rekurencja:",
        "header_force": "Force:",
        "header_files": "Plików:",
        "yes": "tak",
        "no": "nie",
        "with_cover": "z okładką",
        "progress_all": "[bold]Wszystko[/]",
        "progress_left": "[dim]· zostało[/]",
        "table_title": "Wyniki konwersji",
        "col_file": "Plik",
        "col_source": "Źródło",
        "col_opus": "Opus",
        "col_saved": "Zaoszczędzono",
        "col_ratio": "Redukcja",
        "col_audio_time": "Czas audio",
        "col_conv_time": "Czas konw.",
        "col_status": "Status",
        "table_caption": "Pokazano ostatnie {max_rows} z {total} plików",
        "status_skipped": "[dim]⏩ pominięto[/]",
        "status_failed": "[bold red]✗ błąd[/]",
        "summary_title": "[bold cyan]📊 Podsumowanie[/]",
        "summary_converted": "  [bold white]Skonwertowano:[/]  [green bold]{count}[/] plików ({duration} audio)",
        "summary_skipped": "  [bold white]Pominięto:[/]      [dim]{count}[/] plików",
        "summary_failed": "  [bold white]Błędy:[/]          {count}",
        "summary_source": "  [bold white]Rozmiar źródła:[/] [yellow]{size}[/]",
        "summary_opus": "  [bold white]Rozmiar Opus:[/]   [cyan]{size}[/]",
        "summary_saved_ok": "  [bold white]Zaoszczędzono:[/]  [green bold]{size}[/]",
        "summary_saved_neg": "  [bold white]Zaoszczędzono:[/]  [red bold]{size} (output większy!)[/]",
        "summary_speed": "  [bold white]Prędkość:[/]       [dim]{speed:.1f} MB/s[/]",
        "summary_bitrate": "  [bold white]Bitrate:[/]        [cyan]{bitrate}[/]  [dim](64k — mowa+muzyka, 48k — narracja, 80k — pełna produkcja)[/]",
        "summary_failed_hdr": "  [red bold]Pliki z błędem:[/]",
        "delete_prompt": "[yellow]Usunąć oryginalne pliki audio? [t/N][/]",
        "delete_choices": ["t", "n"],
        "delete_default": "n",
        "delete_confirm_val": "t",
        "deleting_status": "[red]Usuwanie plików audio…[/]",
        "delete_error": "[red]  Błąd usuwania {name}: {err}[/]",
        "deleted_success": "  [green]✅ Usunięto {count} plików audio.[/]",
        "deleted_errors": " [red]({count} błędów)[/]",
        "delete_kept": "  [dim]Oryginały zachowane.[/]",
        "cli_desc": "Konwerter plików audio → Opus | Wieloplatformowy",
        "cli_epilog": (
            "Przykłady:\n"
            "  opusbook .                     # konwersja z domyślnym 64k\n"
            "  opusbook audiobooki/ -r        # rekurencyjnie\n"
            "  opusbook sluchowisko/ -b 80k   # pełna produkcja (muzyka+SFX)\n"
            "  opusbook narracja/ -b 48k      # sam lektor, bez muzyki\n"
            "  opusbook . --delete            # konwersja + auto-usunięcie oryginałów"
        ),
        "cli_path_metavar": "ŚCIEŻKA",
        "cli_path_help": "Katalog z plikami audio (domyślnie: bieżący)",
        "cli_bitrate_help": "Bitrate Opus — 64k domyślny (mowa+muzyka), 48k (sama narracja), 80k (pełna produkcja)",
        "cli_jobs_help": "Liczba współbieżnych procesów konwersji (domyślnie: min(4, liczba rdzeni))",
        "cli_recurse_help": "Przeszukuj podkatalogi rekurencyjnie",
        "cli_auto_help": "Auto-bitrate: mono→32k, stereo→z -b (domyślny 64k)",
        "cli_force_help": "Nadpisuj istniejące pliki .opus",
        "cli_keep_help": "Zachowaj oryginały bez pytania",
        "cli_delete_help": "Usuń oryginały bez pytania (bez interakcji)",
        "cli_max_table_help": "Maks. wierszy w tabeli wyników (domyślnie: 30)",
        "cli_dry_run_help": "Pokaż planowane komendy ffmpeg bez uruchamiania",
        "cli_lang_help": "Wymuś język interfejsu (auto, pl, en)",
        "non_tty_bitrate": "[dim]Brak TTY — używam domyślnego bitrate 64k (zmień flagą -b).[/]",
        "aborted": "[red]Przerwano przez użytkownika (Ctrl+C). Czekam na zatrzymanie wątków…[/]",
        "invalid_jobs": "[red]Błędna wartość --jobs: {value!r}. Podaj liczbę całkowitą >= 1.[/]",
        "invalid_max_table": "[red]Błędna wartość --max-table: {value!r}. Podaj liczbę całkowitą >= 1.[/]",
        "delete_keep_conflict": "[red]Opcje --delete i --keep wykluczają się.[/]",
        "unsupported_file": "[red]Niewspierany format audio: {path}[/]",
        "stat_error": "[yellow]Pomijam nieczytelny plik: {path}[/]",
        "dry_run_header": "[bold cyan]DRY-RUN — planowane komendy ffmpeg:[/]",
    },
}

def detect_system_language() -> str:
    for var in ("OPUSBOOK_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "").lower()
        if val.startswith("pl"):
            return "pl"
        elif val.startswith("en"):
            return "en"
    return "en"

_CURRENT_LANG = detect_system_language()

def set_lang(lang: str):
    global _CURRENT_LANG
    if lang in ("pl", "en"):
        _CURRENT_LANG = lang
    elif lang == "auto":
        _CURRENT_LANG = detect_system_language()

def t(key: str, **kwargs) -> str:
    lang_dict = MESSAGES.get(_CURRENT_LANG, MESSAGES["en"])
    template = lang_dict.get(key, MESSAGES["en"].get(key, key))
    if kwargs:
        return template.format(**kwargs)
    return template

# ── Typy danych / Data types ───────────────────────────────────────────────

@dataclass
class ConversionResult:
    name: str
    source: Path
    output: Path
    src_bytes: int
    opus_bytes: int
    duration_s: float
    status: str  # "ok" | "skipped" | "failed"
    audio_duration: float = 0.0
    error: str = ""

    # Backward-compat aliases (old field name was mp3_bytes)
    @property
    def mp3_bytes(self) -> int:
        return self.src_bytes

    @property
    def saved_bytes(self) -> int:
        return self.src_bytes - self.opus_bytes

    @property
    def ratio(self) -> float:
        return (self.saved_bytes / self.src_bytes * 100) if self.src_bytes else 0.0

    @property
    def src_mb(self) -> float:
        return self.src_bytes / 1_048_576

    @property
    def mp3_mb(self) -> float:
        return self.src_mb

    @property
    def opus_mb(self) -> float:
        return self.opus_bytes / 1_048_576

    @property
    def saved_mb(self) -> float:
        return self.saved_bytes / 1_048_576


@dataclass
class Stats:
    results: list[ConversionResult] = field(default_factory=list)
    elapsed_s: float = 0.0  # wall-clock time of whole conversion phase

    @property
    def converted(self):
        return [r for r in self.results if r.status == "ok"]

    @property
    def skipped(self):
        return [r for r in self.results if r.status == "skipped"]

    @property
    def failed(self):
        return [r for r in self.results if r.status == "failed"]

    @property
    def total_mp3_mb(self) -> float:
        return sum(r.src_mb for r in self.converted)

    @property
    def total_opus_mb(self) -> float:
        return sum(r.opus_mb for r in self.converted)

    @property
    def total_saved_mb(self) -> float:
        return self.total_mp3_mb - self.total_opus_mb

    @property
    def total_ratio(self) -> float:
        return (self.total_saved_mb / self.total_mp3_mb * 100) if self.total_mp3_mb else 0.0

    @property
    def avg_speed_mb(self) -> float:
        """Wall-clock throughput in MB/s of source audio."""
        if self.elapsed_s > 0:
            return self.total_mp3_mb / self.elapsed_s if self.total_mp3_mb else 0.0
        total_t = sum(r.duration_s for r in self.converted)
        return self.total_mp3_mb / total_t if total_t > 0 else 0.0


@dataclass
class FileInfo:
    """Metadata collected during audio probing."""
    path: Path
    duration: float = 0.0      # seconds
    channels: int = 0          # 1=mono, 2=stereo, 0=unknown
    has_cover: bool = False


def fmt_duration(seconds: float) -> str:
    """Format duration: '2h 13m 5s' / '13m 5s' / '45s'."""
    if seconds <= 0:
        return "—"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


# ── Formatowanie i UI / Helpers ───────────────────────────────────────────

def fmt_mb(mb: float) -> str:
    if mb >= 1000:
        return f"{mb/1024:.2f} GB"
    return f"{mb:.2f} MB"


def fmt_size_badge(mb: float) -> Text:
    txt = Text(fmt_mb(mb))
    if mb < 10:
        txt.stylize("dim")
    elif mb < 100:
        txt.stylize("cyan")
    else:
        txt.stylize("bright_cyan bold")
    return txt


def ratio_color(ratio: float) -> str:
    if ratio >= 70:
        return "bright_green bold"
    if ratio >= 50:
        return "green"
    if ratio >= 30:
        return "yellow"
    return "red"


class RealtimeSpeedColumn(TextColumn):
    """Shows task.speed as realtime multiplier (e.g. '12.34×')."""

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)

    def render(self, task):
        speed = task.speed
        if speed and speed > 0:
            return Text(f"{speed:.2f}×", style="bright_magenta")
        return Text("—", style="dim")


def fmt_time_code(seconds: float) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    if seconds is None or seconds < 0:
        seconds = 0
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class AudioDurationColumn(TextColumn):
    """Displays audio time progress: HH:MM:SS or MM:SS."""

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)

    def render(self, task):
        completed = fmt_time_code(task.completed)
        total = fmt_time_code(task.total)
        return Text(f"({completed}/{total})", style="cyan")


def _render_arrow_menu(prompt_text: str, options: list[tuple[str, str]], selected: int) -> str:
    """Render arrow navigation menu for Live display."""
    lines = [f"[bold cyan]{prompt_text}[/]"]
    for i, (val, desc) in enumerate(options):
        if i == selected:
            lines.append(f"[reverse]  ▶ [cyan bold]{val}[/]  [dim]{desc}[/]  [/]")
        else:
            lines.append(f"    [dim]{val:<4}[/]  [dim]{desc}[/]")
    lines.append(t("nav_hint"))
    return "\n".join(lines)


def select_with_arrows(
    prompt_text: str,
    options: list[tuple[str, str]],
    default_idx: int = 1,
) -> str:
    """Interactive arrow picker ↑/↓. Returns value of selected option."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return _select_fallback(prompt_text, options, default_idx)

    if sys.platform == "win32":
        return _select_windows(prompt_text, options, default_idx)
    return _select_posix(prompt_text, options, default_idx)


def _select_posix(
    prompt_text: str,
    options: list[tuple[str, str]],
    default_idx: int,
) -> str:
    """Arrow selector for POSIX (Linux/macOS)."""
    import select as _select
    import termios
    import tty

    selected = default_idx
    fd = sys.stdin.fileno()

    try:
        old_settings = termios.tcgetattr(fd)
    except (termios.error, OSError):
        return _select_fallback(prompt_text, options, default_idx)

    def _read_char() -> bytes:
        r, _, _ = _select.select([fd], [], [], 0.05)
        if r:
            return os.read(fd, 1)
        return b""

    def _read_escape() -> str | None:
        c2 = _read_char()
        if not c2:
            return "escape"
        if c2 == b"[":
            c3 = _read_char()
            if c3 == b"A":
                return "up"
            if c3 == b"B":
                return "down"
        return None

    try:
        tty.setcbreak(fd)
        with Live(
            _render_arrow_menu(prompt_text, options, selected),
            console=console,
            refresh_per_second=30,
            transient=False,
        ) as live:
            while True:
                r, _, _ = _select.select([fd], [], [])
                if not r:
                    continue
                ch = os.read(fd, 1)
                if ch in (b"\r", b"\n"):
                    break
                elif ch == b"\x1b":
                    action = _read_escape()
                    if action == "up":
                        selected = (selected - 1) % len(options)
                    elif action == "down":
                        selected = (selected + 1) % len(options)
                    elif action == "escape":
                        raise KeyboardInterrupt
                elif ch == b"\x03":
                    raise KeyboardInterrupt
                elif ch in (b"k", b"K"):
                    selected = (selected - 1) % len(options)
                elif ch in (b"j", b"J"):
                    selected = (selected + 1) % len(options)
                elif ch == b"q":
                    raise KeyboardInterrupt
                elif ch.isdigit():
                    n = int(ch)
                    if 1 <= n <= len(options):
                        selected = n - 1
                live.update(_render_arrow_menu(prompt_text, options, selected))
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except (termios.error, OSError):
            pass
        console.print()

    return options[selected][0]


def _select_fallback(
    prompt_text: str,
    options: list[tuple[str, str]],
    default_idx: int,
) -> str:
    """Numeric fallback when arrows are not supported."""
    all_choices = [str(i + 1) for i in range(len(options))] + [v for v, _ in options]
    result = Prompt.ask(
        prompt_text + t("fallback_prompt_suffix", count=len(options)),
        choices=all_choices,
        default=str(default_idx + 1),
    )
    if result.isdigit():
        return options[int(result) - 1][0]
    return result


def _select_windows(
    prompt_text: str,
    options: list[tuple[str, str]],
    default_idx: int,
) -> str:
    """Arrow selector for Windows (msvcrt)."""
    import msvcrt

    selected = default_idx

    def _read_key() -> str | None:
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            ch2 = msvcrt.getch()
            if ch2 == b"H":
                return "up"
            if ch2 == b"P":
                return "down"
            return None
        if ch in (b"\r", b"\n"):
            return "enter"
        if ch == b"\x1b":
            return "escape"
        if ch == b"\x03":
            raise KeyboardInterrupt
        if ch.isdigit():
            return f"digit_{ch.decode()}"
        try:
            return ch.decode("utf-8").lower()
        except UnicodeDecodeError:
            return None

    try:
        with Live(
            _render_arrow_menu(prompt_text, options, selected),
            console=console,
            refresh_per_second=30,
            transient=False,
        ) as live:
            while True:
                key = _read_key()
                if key == "enter":
                    break
                if key in ("up", "k"):
                    selected = (selected - 1) % len(options)
                elif key in ("down", "j"):
                    selected = (selected + 1) % len(options)
                elif key == "escape" or key == "q":
                    raise KeyboardInterrupt
                elif key and key.startswith("digit_"):
                    n = int(key.split("_")[1])
                    if 1 <= n <= len(options):
                        selected = n - 1
                live.update(_render_arrow_menu(prompt_text, options, selected))
    finally:
        console.print()

    return options[selected][0]


# ── Narzędzia FFmpeg / Probing ─────────────────────────────────────────────

def check_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        console.print(
            Panel(
                t("missing_ffmpeg_body"),
                title=t("missing_ffmpeg_title"),
                border_style="red",
            )
        )
        sys.exit(1)
    return path


def get_ffmpeg_version(ffmpeg_path: str) -> str:
    try:
        out = subprocess.check_output(
            [ffmpeg_path, "-version"], stderr=subprocess.STDOUT, text=True
        )
        m = re.search(r"ffmpeg version (\S+)", out)
        return m.group(1) if m else "?"
    except Exception:
        return "?"


def find_ffprobe() -> str:
    """Finds ffprobe — typically in the same path as ffmpeg."""
    p = shutil.which("ffprobe")
    if p:
        return p
    ff = shutil.which("ffmpeg")
    if ff:
        candidate = Path(ff).parent / "ffprobe"
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return ""


def ffprobe_duration(file: Path, ffprobe: str) -> float:
    """Audio duration in seconds (0.0 on error)."""
    if not ffprobe:
        return 0.0
    try:
        out = subprocess.check_output(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file),
            ],
            stderr=subprocess.DEVNULL, text=True, timeout=10,
        )
        return float(out.strip())
    except Exception:
        return 0.0


def get_file_metadata(file: Path, ffprobe: str) -> tuple[float, int, bool]:
    """Single probe for duration, channel count, and cover art presence."""
    if not ffprobe:
        return 0.0, 0, False
    try:
        out = subprocess.check_output(
            [
                ffprobe, "-v", "error",
                "-print_format", "json",
                "-show_entries", "format=duration",
                "-show_entries", "stream=channels,codec_type",
                str(file),
            ],
            stderr=subprocess.DEVNULL, text=True, timeout=10,
        )
        data = json.loads(out)
        try:
            duration = float(data.get("format", {}).get("duration", 0.0))
        except (TypeError, ValueError):
            duration = 0.0

        channels = 0
        has_cover = False
        for stream in data.get("streams", []):
            ctype = stream.get("codec_type")
            if ctype == "audio" and channels == 0:
                # First audio stream wins (ffprobe a:0 semantics).
                try:
                    channels = int(stream.get("channels", 0))
                except (TypeError, ValueError):
                    channels = 0
            elif ctype == "video":
                has_cover = True
        return duration, channels, has_cover
    except Exception:
        return 0.0, 0, False


def extract_cover(file: Path, cover_path: Path, ffmpeg: str) -> bool:
    """Extracts embedded cover to sidecar cover.jpg (always real JPEG)."""
    try:
        r = subprocess.run(
            [
                ffmpeg, "-y", "-loglevel", "error",
                "-i", str(file),
                "-map", "0:v:0?",
                "-c:v", "mjpeg",
                "-q:v", "2",
                "-frames:v", "1",
                str(cover_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        return r.returncode == 0 and cover_path.exists() and cover_path.stat().st_size > 0
    except Exception:
        return False


def _safe_unlink(path: Path) -> None:
    """Best-effort removal of partial/failed output files."""
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except OSError:
        pass


# ── Konwersja / Conversion ─────────────────────────────────────────────────

def convert_file(
    file: Path,
    bitrate: str,
    force: bool,
    ffmpeg: str,
    ffprobe: str,
    duration: float,
    progress=None,
    inner_task_id=None,
    outer_task_id=None,
    dry_run: bool = False,
    extracted_covers: set[Path] | None = None,
    cover_lock: threading.Lock | None = None,
) -> ConversionResult:
    out = file.with_suffix(".opus")
    try:
        src_bytes = file.stat().st_size
    except OSError as e:
        return ConversionResult(
            name=file.name,
            source=file,
            output=out,
            src_bytes=0,
            opus_bytes=0,
            duration_s=0,
            status="failed",
            audio_duration=duration,
            error=f"unreadable source: {e}"[:200],
        )

    if out.exists() and not force:
        if progress is not None and outer_task_id is not None and duration > 0:
            progress.advance(outer_task_id, duration)
        try:
            existing = out.stat().st_size if out.is_file() else 0
        except OSError:
            existing = 0
        return ConversionResult(
            name=file.name,
            source=file,
            output=out,
            src_bytes=src_bytes,
            opus_bytes=existing,
            duration_s=0,
            status="skipped",
            audio_duration=duration,
        )

    args = [
        ffmpeg,
        "-i", str(file),
        "-map_metadata", "0",
        "-map_chapters", "0",
        "-map", "0:a:0",
        "-c:a", "libopus",
        "-application", "audio",
        "-b:a", bitrate,
        "-vbr", "on",
        "-progress", "pipe:1",
        "-nostats",
        "-y",
        str(out),
    ]

    if dry_run:
        console.print(f"  [dim]DRY:[/] {' '.join(args)}")
        if progress is not None and outer_task_id is not None and duration > 0:
            progress.advance(outer_task_id, duration)
        return ConversionResult(
            name=file.name,
            source=file,
            output=out,
            src_bytes=src_bytes,
            opus_bytes=0,
            duration_s=0,
            status="skipped",
            audio_duration=duration,
            error="dry-run",
        )

    t0 = time.perf_counter()
    stderr_chunks: list[str] = []
    proc = None
    last_sec = 0.0

    def _drain_stderr():
        if proc and proc.stderr:
            try:
                data = proc.stderr.read()
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="replace")
                stderr_chunks.append(data)
            except Exception:
                pass

    def _advance(delta: float):
        if delta <= 0 or progress is None:
            return
        try:
            if inner_task_id is not None:
                progress.advance(inner_task_id, delta)
            if outer_task_id is not None:
                progress.advance(outer_task_id, delta)
        except Exception:
            pass

    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        if proc.stdout:
            for line in proc.stdout:
                line = line.strip()
                if line.startswith("out_time_us="):
                    try:
                        us = int(line.split("=", 1)[1])
                        sec = max(0.0, us / 1_000_000.0)
                        if duration > 0:
                            sec = min(sec, duration)
                        delta = sec - last_sec
                        if delta > 0:
                            _advance(delta)
                            last_sec = sec
                    except ValueError:
                        pass
                elif line == "progress=end":
                    break

        proc.wait()
        stderr_thread.join(timeout=2)
        duration_s = time.perf_counter() - t0

        delta_remaining = duration - last_sec
        if delta_remaining > 0:
            _advance(delta_remaining)

        if proc.returncode != 0:
            err = "".join(stderr_chunks).strip()[:200]
            _safe_unlink(out)
            return ConversionResult(
                name=file.name,
                source=file,
                output=out,
                src_bytes=src_bytes,
                opus_bytes=0,
                duration_s=duration_s,
                status="failed",
                audio_duration=duration,
                error=err or f"ffmpeg exit {proc.returncode}",
            )

        if duration > 0:
            out_dur = ffprobe_duration(out, ffprobe)
            if out_dur == 0 or abs(out_dur - duration) / duration > 0.05:
                err = (f"output duration {out_dur:.1f}s != source {duration:.1f}s"
                       if out_dur else "output has no audio stream")
                _safe_unlink(out)
                return ConversionResult(
                    name=file.name,
                    source=file,
                    output=out,
                    src_bytes=src_bytes,
                    opus_bytes=0,
                    duration_s=duration_s,
                    status="failed",
                    audio_duration=duration,
                    error=err,
                )

        if extracted_covers is not None:
            cover_path = file.parent / "cover.jpg"
            if cover_lock is not None:
                with cover_lock:
                    if cover_path not in extracted_covers:
                        if cover_path.exists():
                            extracted_covers.add(cover_path)
                        elif extract_cover(file, cover_path, ffmpeg):
                            extracted_covers.add(cover_path)
            elif cover_path not in extracted_covers:
                if cover_path.exists():
                    extracted_covers.add(cover_path)
                elif extract_cover(file, cover_path, ffmpeg):
                    extracted_covers.add(cover_path)

        try:
            opus_bytes = out.stat().st_size if out.exists() else 0
        except OSError:
            opus_bytes = 0
        return ConversionResult(
            name=file.name,
            source=file,
            output=out,
            src_bytes=src_bytes,
            opus_bytes=opus_bytes,
            duration_s=duration_s,
            status="ok",
            audio_duration=duration,
        )

    except Exception as e:
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
        _safe_unlink(out)
        delta_remaining = duration - last_sec
        if delta_remaining > 0 and progress is not None and outer_task_id is not None:
            try:
                progress.advance(outer_task_id, delta_remaining)
            except Exception:
                pass
        return ConversionResult(
            name=file.name,
            source=file,
            output=out,
            src_bytes=src_bytes,
            opus_bytes=0,
            duration_s=0,
            status="failed",
            audio_duration=duration,
            error=str(e)[:200],
        )


# ── Tabela i Podsumowanie / UI ─────────────────────────────────────────────

def _display_name(result: ConversionResult, base_dir: Path | None) -> str:
    """Human-readable path: relative to base_dir when possible (fixes -r collisions)."""
    try:
        if base_dir is not None:
            return str(result.source.relative_to(base_dir))
    except (ValueError, OSError):
        pass
    return result.name


def build_result_table(stats: Stats, max_rows: int = 30, base_dir: Path | None = None) -> Table:
    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="bright_black",
        row_styles=["", "dim"],
        expand=True,
        title=f"[bold]{t('table_title')}[/]",
        title_style="bold white",
    )

    table.add_column(t("col_file"), style="white", no_wrap=False, ratio=1)
    table.add_column(t("col_source"), justify="right", style="yellow", no_wrap=True)
    table.add_column(t("col_opus"), justify="right", style="cyan", no_wrap=True)
    table.add_column(t("col_saved"), justify="right", no_wrap=True)
    table.add_column(t("col_ratio"), justify="right", no_wrap=True)
    table.add_column(t("col_audio_time"), justify="right", style="dim", no_wrap=True)
    table.add_column(t("col_conv_time"), justify="right", style="dim", no_wrap=True)
    table.add_column(t("col_status"), justify="center", no_wrap=True)

    converted = stats.converted
    if len(converted) > max_rows:
        shown = converted[-max_rows:]
        table.caption = (
            f"[dim]{t('table_caption', max_rows=max_rows, total=len(converted))}[/]"
        )
    else:
        shown = converted

    for r in shown:
        ratio_str = f"{r.ratio:.1f}%"
        style = ratio_color(r.ratio)
        saved = fmt_mb(r.saved_mb)
        if r.saved_mb > 0:
            saved_cell = f"[green]{saved}[/]"
        elif r.saved_mb < 0:
            saved_cell = f"[red]{saved}[/]"
        else:
            saved_cell = saved
        table.add_row(
            _display_name(r, base_dir),
            fmt_mb(r.src_mb),
            fmt_mb(r.opus_mb),
            saved_cell,
            f"[{style}]{ratio_str}[/]",
            fmt_duration(r.audio_duration),
            f"{r.duration_s:.1f}s",
            "[bold green]✓[/]",
        )

    for r in stats.skipped:
        table.add_row(
            _display_name(r, base_dir),
            fmt_mb(r.src_mb),
            "[dim]—[/]",
            "[dim]—[/]",
            "[dim]—[/]",
            fmt_duration(r.audio_duration),
            "[dim]—[/]",
            t("status_skipped"),
        )

    for r in stats.failed:
        table.add_row(
            _display_name(r, base_dir),
            fmt_mb(r.src_mb),
            "[dim]—[/]",
            "[dim]—[/]",
            "[dim]—[/]",
            fmt_duration(r.audio_duration),
            f"{r.duration_s:.1f}s" if r.duration_s > 0 else "[dim]—[/]",
            t("status_failed"),
        )

    return table


def build_summary_panel(stats: Stats, bitrate: str) -> Panel:
    ratio = stats.total_ratio
    bar_len = 30
    clamped = max(0.0, min(100.0, ratio))
    filled = int(bar_len * clamped / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    bar_style = ratio_color(ratio)

    total_audio_s = sum(r.audio_duration for r in stats.converted)
    if stats.total_saved_mb >= 0:
        saved_line = t("summary_saved_ok", size=fmt_mb(stats.total_saved_mb))
    else:
        saved_line = t("summary_saved_neg", size=fmt_mb(stats.total_saved_mb))
    lines = [
        t("summary_converted", count=len(stats.converted), duration=fmt_duration(total_audio_s)),
        t("summary_skipped", count=len(stats.skipped)),
        t("summary_failed", count=('[red bold]' + str(len(stats.failed)) + '[/]' if stats.failed else '[dim]0[/]')),
        "",
        t("summary_source", size=fmt_mb(stats.total_mp3_mb)),
        t("summary_opus", size=fmt_mb(stats.total_opus_mb)),
        saved_line,
        "",
        f"  [{bar_style}]{bar}[/] [{bar_style}]{ratio:.1f}%[/]",
        "",
        t("summary_speed", speed=stats.avg_speed_mb),
        t("summary_bitrate", bitrate=bitrate),
    ]

    if stats.failed:
        lines += ["", t("summary_failed_hdr")]
        for r in stats.failed:
            err_short = r.error[:80] + "…" if len(r.error) > 80 else r.error
            lines.append(f"    [red]• {r.name}[/] — [dim]{err_short}[/]")

    return Panel(
        "\n".join(lines),
        title=t("summary_title"),
        border_style="cyan",
        padding=(1, 2),
    )


# ── Główna logika / CLI Entrypoint ─────────────────────────────────────────

def main(argv: list[str] | None = None):
    # Pre-parse language argument early to set correct locale for --help
    raw_argv = sys.argv[1:] if argv is None else argv
    early_lang = None
    for i, arg in enumerate(raw_argv):
        if arg in ("--lang", "-l") and i + 1 < len(raw_argv):
            early_lang = raw_argv[i + 1]
        elif arg.startswith("--lang="):
            early_lang = arg.split("=", 1)[1]
    if early_lang:
        set_lang(early_lang)

    parser = argparse.ArgumentParser(
        prog="opusbook",
        description=t("cli_desc"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=t("cli_epilog"),
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        metavar=t("cli_path_metavar"),
        help=t("cli_path_help"),
    )
    parser.add_argument(
        "-b", "--bitrate",
        default=None,
        metavar="BITRATE",
        help=t("cli_bitrate_help"),
    )
    parser.add_argument(
        "-j", "--jobs",
        type=int,
        default=min(4, os.cpu_count() or 1),
        metavar="N",
        help=t("cli_jobs_help"),
    )
    parser.add_argument(
        "-r", "--recurse",
        action="store_true",
        help=t("cli_recurse_help"),
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help=t("cli_auto_help"),
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help=t("cli_force_help"),
    )
    keep_delete = parser.add_mutually_exclusive_group()
    keep_delete.add_argument(
        "--keep",
        action="store_true",
        help=t("cli_keep_help"),
    )
    keep_delete.add_argument(
        "--delete",
        action="store_true",
        help=t("cli_delete_help"),
    )
    parser.add_argument(
        "--max-table",
        type=int,
        default=30,
        metavar="N",
        help=t("cli_max_table_help"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=t("cli_dry_run_help"),
    )
    parser.add_argument(
        "--lang", "-l",
        choices=["auto", "en", "pl"],
        default="auto",
        help=t("cli_lang_help"),
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args(raw_argv)

    # Apply explicit language if provided
    if args.lang != "auto":
        set_lang(args.lang)

    if args.jobs is None or args.jobs < 1:
        console.print(t("invalid_jobs", value=args.jobs))
        sys.exit(2)
    if args.max_table is None or args.max_table < 1:
        console.print(t("invalid_max_table", value=args.max_table))
        sys.exit(2)

    # Interactive bitrate selection if not provided.
    # Non-TTY (cron/CI) must not block: fall back to 64k.
    if args.bitrate is None:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            console.print(t("non_tty_bitrate"))
            args.bitrate = "64k"
        else:
            try:
                args.bitrate = select_with_arrows(
                    t("bitrate_prompt"),
                    options=[
                        ("48k", t("bitrate_48k")),
                        ("64k", t("bitrate_64k")),
                        ("80k", t("bitrate_80k")),
                    ],
                    default_idx=1,
                )
            except (EOFError, OSError):
                console.print(t("non_tty_bitrate"))
                args.bitrate = "64k"

    # Bitrate validation
    if not re.match(r"^\d{1,4}[kM]$", args.bitrate):
        console.print(t("invalid_bitrate", bitrate=args.bitrate))
        sys.exit(1)

    try:
        bitrate_num = int(args.bitrate[:-1])
        bitrate_unit = args.bitrate[-1]
        bitrate_kbps = bitrate_num * (1000 if bitrate_unit == "M" else 1)
        if bitrate_kbps < 32:
            console.print(t("bitrate_low_warn"))
        elif bitrate_kbps > 256:
            console.print(t("bitrate_high_warn"))
    except ValueError:
        pass

    root = Path(args.path).resolve()
    if not root.exists():
        console.print(t("path_not_found", path=root))
        sys.exit(1)

    # ── ffmpeg + ffprobe ──
    ffmpeg = check_ffmpeg()
    ffver = get_ffmpeg_version(ffmpeg)
    ffprobe = find_ffprobe()
    if not ffprobe:
        console.print(
            Panel(
                t("missing_ffprobe_body"),
                title=t("missing_ffprobe_title"),
                border_style="red",
            )
        )
        sys.exit(1)
    # Skip ffprobe hard requirement for pure dry-run without metadata? No —
    # dry-run still needs durations for planning, keep requirement.
    console.print(
        f"  [dim]ffmpeg {ffver} → {ffmpeg}[/]\n"
        f"  [dim]ffprobe → {ffprobe}[/]\n"
    )

    # ── Skanowanie plików / Scanning ──
    # Single-file mode: `opusbook song.mp3` converts just that file.
    single_file_mode = root.is_file()
    with console.status(t("scanning_files"), spinner="dots"):
        if single_file_mode:
            if root.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                raw_files = [root]
            else:
                console.print(t("unsupported_file", path=root))
                sys.exit(1)
            scan_base = root.parent
        elif root.is_dir():
            scan_base = root
            if args.recurse:
                raw_files = sorted(
                    [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS]
                )
            else:
                raw_files = sorted(
                    [p for p in root.glob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS]
                )
        else:
            console.print(t("path_not_found", path=root))
            sys.exit(1)

    if not raw_files:
        console.print(
            Panel(
                t("no_audio_files", exts=', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS)), path=root),
                border_style="yellow",
            )
        )
        sys.exit(0)

    # ── Pobieranie metadanych / Probing metadata ──
    file_infos: list[FileInfo] = []
    try:
        with console.status(t("probing_metadata"), spinner="dots") as status:
            def get_meta(p):
                duration, channels, has_cover = get_file_metadata(p, ffprobe)
                return FileInfo(path=p, duration=duration, channels=channels, has_cover=has_cover)

            with ThreadPoolExecutor(max_workers=min(16, (os.cpu_count() or 1) * 2)) as executor:
                for i, info in enumerate(executor.map(get_meta, raw_files), 1):
                    status.update(t("probing_status", i=i, total=len(raw_files), name=info.path.name[:30]))
                    file_infos.append(info)
    except KeyboardInterrupt:
        console.print(t("aborted"))
        sys.exit(130)

    def _safe_size(p: Path) -> int:
        try:
            return p.stat().st_size
        except OSError:
            try:
                console.print(t("stat_error", path=p))
            except Exception:
                pass
            return 0

    total_mp3_mb = sum(_safe_size(info.path) for info in file_infos) / 1_048_576
    total_seconds = sum(info.duration for info in file_infos)
    covers_count = sum(1 for info in file_infos if info.has_cover)
    mono_count = sum(1 for info in file_infos if info.channels == 1)

    # ── Nagłówek informacyjny / Info panel ──
    yes_str = t("yes")
    no_str = t("no")
    header_line = (
        f"{t('header_title')}\n"
        f"[dim]{t('header_dir')}[/] [white]{root}[/]  "
        f"[dim]{t('header_bitrate')}[/] [yellow]{args.bitrate}[/]  "
        f"[dim]{t('header_jobs')}[/] [yellow]{args.jobs}[/]  "
        f"[dim]{t('header_auto')}[/] {'[green]' + yes_str + '[/]' if args.auto else '[dim]' + no_str + '[/]'}  "
        f"[dim]{t('header_recurse')}[/] {'[green]' + yes_str + '[/]' if args.recurse else '[dim]' + no_str + '[/]'}  "
        f"[dim]{t('header_force')}[/] {'[yellow]' + yes_str + '[/]' if args.force else '[dim]' + no_str + '[/]'}\n"
        f"[dim]{t('header_files')}[/] [bold]{len(file_infos)}[/]  "
        f"[dim]({fmt_mb(total_mp3_mb)}, [bold]{fmt_duration(total_seconds)}[/] audio)[/]"
    )
    if args.auto and mono_count:
        header_line += f"  [dim]· {mono_count} mono, {len(file_infos)-mono_count} stereo[/]"
    if covers_count:
        header_line += f"  [dim]· {covers_count} {t('with_cover')}[/]"

    console.print()
    console.print(Panel.fit(header_line, border_style="cyan"))

    stats = Stats()
    extracted_covers: set[Path] = set()
    cover_lock = threading.Lock()
    stats_lock = threading.Lock()

    # ── DRY-RUN: no Live progress (workers would corrupt UI) ──
    if args.dry_run:
        console.print()
        console.print(t("dry_run_header"))
        for info in file_infos:
            effective = "32k" if (args.auto and info.channels == 1) else args.bitrate
            result = convert_file(
                file=info.path,
                bitrate=effective,
                force=args.force,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                duration=info.duration,
                progress=None,
                inner_task_id=None,
                outer_task_id=None,
                dry_run=True,
                extracted_covers=None,
                cover_lock=None,
            )
            with stats_lock:
                stats.results.append(result)
        stats.results.sort(key=lambda r: str(r.source))
        console.print()
        console.print(build_result_table(stats, max_rows=args.max_table, base_dir=scan_base))
        console.print()
        console.print(build_summary_panel(stats, args.bitrate))
        console.print()
        return

    # ── Pasek postępu / Progress bar ──
    progress = Progress(
        SpinnerColumn(spinner_name="arc"),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        AudioDurationColumn(),
        TimeElapsedColumn(),
        TextColumn(t("progress_left")),
        TimeRemainingColumn(),
        RealtimeSpeedColumn(),
        console=console,
        expand=True,
        transient=False,
    )

    outer_task = progress.add_task(
        t("progress_all"),
        total=max(total_seconds, 0.001),
    )

    def convert_worker(info, inner_task):
        effective_bitrate = args.bitrate
        if args.auto and info.channels == 1:
            effective_bitrate = "32k"
        result = convert_file(
            file=info.path,
            bitrate=effective_bitrate,
            force=args.force,
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            duration=info.duration,
            progress=progress,
            inner_task_id=inner_task,
            outer_task_id=outer_task,
            dry_run=False,
            extracted_covers=extracted_covers,
            cover_lock=cover_lock,
        )
        with stats_lock:
            stats.results.append(result)

    wall_start = time.perf_counter()
    try:
        with progress:
            # Manual executor (not `with`) so Ctrl+C can cancel pending futures.
            executor = ThreadPoolExecutor(max_workers=args.jobs)
            try:
                future_to_info = {}
                for info in file_infos:
                    effective = "32k" if (args.auto and info.channels == 1) else args.bitrate
                    suffix = (
                        f"  [dim]([magenta]{effective}[/])[/]"
                        if args.auto and info.channels == 1 else ""
                    )
                    inner = progress.add_task(
                        f"  [cyan]└─ {info.path.name[:42]}[/]" + suffix,
                        total=max(info.duration, 0.001),
                    )
                    fut = executor.submit(convert_worker, info, inner)
                    # Attach inner task id for cleanup on completion.
                    fut._opus_inner = inner  # type: ignore[attr-defined]
                    future_to_info[fut] = info
                for fut in as_completed(future_to_info):
                    inner = getattr(fut, "_opus_inner", None)
                    try:
                        fut.result()
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        # Never let one file kill the whole batch; record failure.
                        info = future_to_info[fut]
                        with stats_lock:
                            try:
                                src_sz = info.path.stat().st_size
                            except OSError:
                                src_sz = 0
                            stats.results.append(
                                ConversionResult(
                                    name=info.path.name,
                                    source=info.path,
                                    output=info.path.with_suffix(".opus"),
                                    src_bytes=src_sz,
                                    opus_bytes=0,
                                    duration_s=0,
                                    status="failed",
                                    audio_duration=info.duration,
                                    error=str(e)[:200],
                                )
                            )
                    finally:
                        if inner is not None:
                            try:
                                progress.remove_task(inner)
                            except Exception:
                                pass
            except KeyboardInterrupt:
                console.print(t("aborted"))
                try:
                    executor.shutdown(cancel_futures=True, wait=False)
                except TypeError:
                    # Python < 3.9 fallback (cancel_futures unsupported)
                    executor.shutdown(wait=False)
                sys.exit(130)
            else:
                executor.shutdown(wait=True)
    except KeyboardInterrupt:
        console.print(t("aborted"))
        sys.exit(130)
    finally:
        try:
            progress.stop()
        except Exception:
            pass
    stats.elapsed_s = time.perf_counter() - wall_start

    stats.results.sort(key=lambda r: str(r.source))

    # ── Wyniki / Results ──
    console.print()
    if stats.converted or stats.skipped or stats.failed:
        console.print(build_result_table(stats, max_rows=args.max_table, base_dir=scan_base))

    console.print()
    console.print(build_summary_panel(stats, args.bitrate))

    # ── Usuwanie oryginałów / Clean up source files ──
    if stats.converted:
        console.print()
        if args.delete:
            do_delete = True
        elif args.keep:
            do_delete = False
        elif not sys.stdin.isatty():
            # Non-interactive without explicit flag → keep (safe default).
            do_delete = False
        else:
            try:
                do_delete = Prompt.ask(
                    t("delete_prompt"),
                    choices=MESSAGES[_CURRENT_LANG]["delete_choices"],
                    default=MESSAGES[_CURRENT_LANG]["delete_default"],
                    console=console,
                ) == MESSAGES[_CURRENT_LANG]["delete_confirm_val"]
            except (EOFError, OSError):
                do_delete = False

        if do_delete:
            deleted, failed_del = 0, 0
            with console.status(t("deleting_status"), spinner="dots"):
                for r in stats.converted:
                    try:
                        r.source.unlink()
                        deleted += 1
                    except Exception as e:
                        console.print(t("delete_error", name=r.name, err=e))
                        failed_del += 1
            err_msg = t("deleted_errors", count=failed_del) if failed_del else ""
            console.print(t("deleted_success", count=deleted) + err_msg)
        else:
            console.print(t("delete_kept"))

    console.print()


if __name__ == "__main__":
    main()
