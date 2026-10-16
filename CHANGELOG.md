# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-09-23

### Added
- **Single-file input support:** `opusbook path/to/file.mp3` converts a single audio file directly.
- **Version flag:** Added `-V` / `--version` CLI options.
- **Automated test suite:** Added comprehensive unit and integration tests with mocked and end-to-end fixtures (`tests/test_opusbook.py`).
- **Development & CI tooling:** Added `ruff` linting, `pytest` configuration, and GitHub Actions test matrix across Python 3.10–3.13 with FFmpeg.
- **Enhanced documentation:** Added troubleshooting guide, accurate storage savings metrics, developer setup, and corrected CLI parameter documentation in both English and Polish.

### Changed
- **Audio stream mapping:** Standardized ffmpeg mapping to the primary audio track (`-map 0:a:0`) to prevent multi-stream issues in players.
- **Cover art encoding:** Transcoding extracted covers to JPEG (`-c:v mjpeg`) to ensure valid image format regardless of source container format.
- **Throughput calculation:** Switched `Speed` metric to real wall-clock elapsed time instead of accumulated worker thread runtimes.
- **Relative path display:** Results table now shows paths relative to the scan directory to eliminate filename collisions during recursive runs (`-r`).
- **Negative savings styling:** Displays negative space savings and expansion in red when output file exceeds source size.
- **Headless & Non-TTY behavior:** Automatically defaults to 64k bitrate when running without a TTY (cron/CI) and safely defaults source file deletion prompt to keep.
- **Clean dry-run display:** Decoupled `--dry-run` output from the interactive progress bar to avoid terminal flicker.
- **Python requirement:** Updated minimum Python requirement to `>= 3.10` in `pyproject.toml` and enabled `from __future__ import annotations`.

### Fixed
- **Partial file cleanup:** Corrupt or interrupted `.opus` outputs are now unlinked immediately upon conversion failure or length mismatch to prevent silent skipping on subsequent runs.
- **Argument validation:** Added strict positive integer validation (`>= 1`) for `--jobs` and `--max-table`.
- **Option exclusivity:** Made `--delete` and `--keep` mutually exclusive in argument parsing.
- **Interrupt handling:** Added graceful `Ctrl+C` (SIGINT) handling with pending task cancellation (`cancel_futures=True`) and child process termination (exit code 130).
- **Filesystem resilience:** Wrapped `stat()` calls in error handlers to safely skip unreadable or deleted files without crashing the batch run.
- **Dead code removal:** Cleaned up unused legacy ffprobe helper functions (`ffprobe_channels`, `ffprobe_has_cover`).

## [1.0.0] - 2026-09-22

### Added
- Initial release of `opusbook`.
- Multi-format audio converter (`.mp3`, `.m4b`, `.m4a`, `.flac`, `.aac`, `.wav`, `.ogg`, `.wma`) to Opus.
- Rich terminal UI with progress bars, summary statistics, and interactive bitrate selection.
- Automatic channel optimization (`--auto`: mono to 32k, stereo to target bitrate).
- Embedded cover art extraction to sidecar `cover.jpg` for Audiobookshelf.
- Recursive directory scanning (`-r`), multi-threading (`-j`), and dry-run mode (`--dry-run`).
