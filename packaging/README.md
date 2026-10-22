# Portable packages

Release downloads contain Python, FFmpeg and ffprobe. Keep the complete extracted
folder together. Both builders write a SHA-256 sidecar and a `BUILD.json` containing
the converter source hash. Native libraries and third-party notices are bundled.

## Linux x86_64

Build on **Debian 13 (trixie)** using Docker or rootless Podman:

```bash
podman build -f packaging/Dockerfile.linux -t opusbook-build-linux packaging
podman run --rm -v "$PWD:/src" opusbook-build-linux
```

Output: `dist/opusbook-<version>-linux-x64.tar.gz` and `.tar.gz.sha256`.
Requires **glibc 2.41+**; Alpine/musl and older systems should use the Python
installation described in the main README. The Linux launcher keeps the standard
CLI; use `-r --keep` for recursive conversion with source preservation.

PyInstaller collects Debian's FFmpeg executables and their linked libraries.
Adjacent shell launchers select those libraries even with an empty PATH.
`third-party/debian-packages.tsv` records the exact package/source versions;
`third-party/debian/` contains Debian copyright and license notices. Rebuilding
may pick up updated Debian packages; `BUILD.json` records the bundled FFmpeg.

Verify and test the extracted archive:

```bash
cd dist
sha256sum -c opusbook-*.tar.gz.sha256
mkdir -p 'portable smoke'
tar -xzf opusbook-1.1.1-linux-x64.tar.gz -C 'portable smoke'
python3 ../packaging/smoke_portable.py 'portable smoke/opusbook/opusbook'
```

The `Linux portable archive` workflow builds on Debian 13 and tests the extracted
archive in a separate Python-only Debian 13 container, without system FFmpeg.

## Windows x64

Build on Windows 10/11 with 64-bit Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" pyinstaller==6.22.0
.\.venv\Scripts\python.exe packaging/build_windows.py
```

The builder downloads a fixed [Gyan FFmpeg essentials build](https://www.gyan.dev/ffmpeg/builds/)
and verifies its SHA-256. For an offline build, pass
`--ffmpeg-archive <downloaded-zip>`; the same checksum is checked.
Output: `dist/opusbook-<version>-windows-x64.zip` and `.zip.sha256`.

No arguments or a single path starts portable mode: prompt for a path if needed,
search recursively, preserve sources, and wait for Enter when attached to a
terminal. Explicit options use the standard CLI. Only one dropped item is supported.

After extracting the ZIP:

```powershell
.\.venv\Scripts\python.exe packaging/smoke_portable.py .\dist\extracted\opusbook\opusbook.exe
```

The `Windows portable ZIP` workflow runs the source tests and extracted-executable
smoke on native Windows. Interactive arrow keys, Explorer drag-and-drop and Ctrl+C
during encoding still require manual Windows verification; redirected-input smoke
does not certify those interactions.

## Validation and publishing

Both workflows run on pushes to `main`, version tags, pull requests and manual
dispatch. They upload archives after tests pass; they do not publish Releases.
Actions downloads contain an outer artifact archive; extract the portable package
inside it. Release assets can be downloaded directly without that extra layer.

The shared smoke runs with an empty PATH and covers help/version, Unicode and
space-containing paths, recursive conversion, source preservation, cover extraction,
skipping existing output, forced replacement, validated deletion and invalid input.
Source regressions also check race handling and artifact validation. POSIX-only tests
are skipped on Windows; the Windows ChangeTime test is skipped on Linux.

The historical `v1.1.1` tag is retained. Portable assets include later hardening and
packaging changes; the Release notes identify their exact commit, and a separate
portable-source archive matches that commit. GitHub's automatic source archives
continue to refer to the historical tag.

JavaScript actions are pinned to reviewed release commit IDs. Before they run,
the workflow checks the runner's bundled Node 24 and updates versions older than
24.22.1 using official Node.js archives with pinned SHA-256 checksums. Newer
runner versions are retained. This covers the October 21, 2026 security fixes
while hosted runner images catch up; Node.js is not part of the portable packages.
