"""Build the portable x64 ZIP on Windows: python packaging/build_windows.py."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FFMPEG_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/"
    "ffmpeg-9.0.2-essentials_build.zip"
)
FFMPEG_SHA256 = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg-archive", type=Path, help="Use a downloaded ZIP (SHA-256 still verified)")
    args = parser.parse_args()
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        raise SystemExit("Build requires 64-bit Python on Windows.")
    with tempfile.TemporaryDirectory(prefix="opusbook-build-") as workspace:
        work = Path(workspace)
        archive = work / "ffmpeg.zip"
        if args.ffmpeg_archive:
            shutil.copy2(args.ffmpeg_archive, archive)
        else:
            print(f"Downloading {FFMPEG_URL}", flush=True)
            with urllib.request.urlopen(FFMPEG_URL, timeout=120) as source, archive.open("wb") as target:
                shutil.copyfileobj(source, target)
        digest = sha256_file(archive)
        if digest != FFMPEG_SHA256:
            raise SystemExit("FFmpeg SHA-256 mismatch; refusing to package.")

        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
            "--console", "--name", "opusbook", "--paths", str(ROOT),
            "--distpath", str(work / "dist"), "--workpath", str(work / "build"),
            "--specpath", str(work), str(ROOT / "packaging" / "windows_entry.py"),
        ], cwd=ROOT, check=True)
        bundle = work / "dist" / "opusbook"
        notices = bundle / "third-party"
        notices.mkdir()
        with zipfile.ZipFile(archive) as package:
            # Read exact members only; never extract untrusted archive paths.
            prefix = "ffmpeg-9.0.2-essentials_build/"
            for name in ("ffmpeg.exe", "ffprobe.exe"):
                with package.open(prefix + "bin/" + name) as source, (bundle / name).open("wb") as target:
                    shutil.copyfileobj(source, target)
            for name in ("LICENSE", "README.txt"):
                (notices / ("ffmpeg-" + name)).write_bytes(package.read(prefix + name))
        (notices / "ffmpeg-source.txt").write_text(
            f"Unmodified FFmpeg executables from {FFMPEG_URL}\nSHA256: {digest}\n"
            "Build provider: https://www.gyan.dev/ffmpeg/builds/\n"
            "FFmpeg source: https://github.com/FFmpeg/FFmpeg/tree/946fcce07b\n"
            "External library versions: see ffmpeg-README.txt.\n",
            encoding="utf-8",
        )
        for name in ("rich", "pygments", "markdown-it-py", "mdurl", "pyinstaller"):
            distribution = importlib.metadata.distribution(name)
            for entry in distribution.files or []:
                if "license" in str(entry).lower() or "copying" in str(entry).lower():
                    source = Path(distribution.locate_file(entry))
                    if source.is_file():
                        dest = notices / name / Path(str(entry))
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, dest)
        shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", notices / "Python-LICENSE.txt")
        shutil.copy2(ROOT / "LICENSE", bundle)
        shutil.copy2(ROOT / "packaging" / "windows-README.txt", bundle / "README.txt")
        version = importlib.metadata.version("opusbook")
        (bundle / "BUILD.json").write_text(json.dumps({
            "opusbook": version, "python": sys.version,
            "source_sha256": sha256_file(ROOT / "opusbook.py"),
            "entry_sha256": sha256_file(ROOT / "packaging" / "windows_entry.py"),
            "pyinstaller": importlib.metadata.version("pyinstaller"),
            "ffmpeg_url": FFMPEG_URL, "ffmpeg_sha256": digest,
        }, indent=2), encoding="utf-8")
        output = ROOT / "dist"
        output.mkdir(exist_ok=True)
        destination = output / f"opusbook-{version}-windows-x64"
        zip_path = Path(shutil.make_archive(str(destination), "zip", bundle.parent, bundle.name))
        checksum = sha256_file(zip_path)
        zip_path.with_suffix(".zip.sha256").write_text(
            f"{checksum}  {zip_path.name}\n", encoding="ascii",
        )
        print(zip_path)


if __name__ == "__main__":
    main()
