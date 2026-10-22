"""Build inside packaging/Dockerfile.linux for the glibc 2.41 baseline."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise SystemExit("Build requires Linux x86_64.")
    if platform.libc_ver() != ("glibc", "2.41"):
        raise SystemExit("Use packaging/Dockerfile.linux (glibc 2.41).")
    with tempfile.TemporaryDirectory(prefix="opusbook-build-") as workspace:
        work = Path(workspace)
        # PyInstaller deliberately filters some desktop libraries (e.g. libdrm).
        # FFmpeg links them even for audio-only use, so collect its full closure.
        binaries = {Path("/usr/bin/ffmpeg"), Path("/usr/bin/ffprobe")}
        system_libraries = re.compile(r"^(ld-linux|lib(c|m|dl|pthread|rt|util|resolv|nss_[^.]+)\.so)")
        for executable in ("/usr/bin/ffmpeg", "/usr/bin/ffprobe"):
            dependencies = subprocess.check_output(["ldd", executable], text=True)
            if "not found" in dependencies:
                raise SystemExit(f"Unresolved dependencies: {dependencies}")
            for path in re.findall(r"(?:=>\s+|^\s*)(/\S+)", dependencies, re.MULTILINE):
                library = Path(path)
                if not system_libraries.match(library.name):
                    binaries.add(library)
        binary_args = [arg for path in sorted(binaries) for arg in ("--add-binary", f"{path}:.")]
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
            "--console", "--name", "opusbook", "--paths", str(ROOT),
            *binary_args,
            "--distpath", str(work / "dist"), "--workpath", str(work / "build"),
            "--specpath", str(work), str(ROOT / "packaging" / "linux_entry.py"),
        ], cwd=ROOT, check=True)
        bundle = work / "dist" / "opusbook"
        for name in ("ffmpeg", "ffprobe"):
            launcher = bundle / name
            launcher.write_text(
                '#!/bin/sh\n'
                'bundle_dir=$(CDPATH= cd -- "${0%/*}" && pwd) || exit 1\n'
                'export LD_LIBRARY_PATH="$bundle_dir/_internal"\n'
                f'exec "$bundle_dir/_internal/{name}" "$@"\n', encoding="utf-8",
            )
            launcher.chmod(0o755)
        notices = bundle / "third-party"
        notices.mkdir()
        # Debian copyright files include the licenses of native dependencies.
        for copyright_file in Path("/usr/share/doc").glob("*/copyright"):
            dest = notices / "debian" / copyright_file.parent.name
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(copyright_file, dest / "copyright")
        for name in ("rich", "pygments", "markdown-it-py", "mdurl", "pyinstaller"):
            distribution = importlib.metadata.distribution(name)
            for entry in distribution.files or []:
                if "license" in str(entry).lower() or "copying" in str(entry).lower():
                    source = Path(distribution.locate_file(entry))
                    if source.is_file():
                        dest = notices / name / Path(str(entry))
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, dest)
        import sysconfig
        shutil.copy2(Path(sysconfig.get_path("stdlib")) / "LICENSE.txt", notices / "Python-LICENSE.txt")
        shutil.copy2(ROOT / "LICENSE", bundle)
        shutil.copy2(ROOT / "packaging" / "linux-README.txt", bundle / "README.txt")
        packages = subprocess.check_output([
            "dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n",
        ], text=True)
        (notices / "debian-packages.tsv").write_text(packages, encoding="utf-8")
        (notices / "sources.txt").write_text(
            "Native binaries and libraries: Debian 13 packages.\n"
            "Exact package/source versions: debian-packages.tsv\n"
            "Source archives: https://snapshot.debian.org/ and https://sources.debian.org/\n"
            "Python: https://www.python.org/downloads/source/\n", encoding="utf-8",
        )
        # Read the version from the actual source, not a stale installed wheel.
        sys.path.insert(0, str(ROOT))
        import opusbook
        version = opusbook.__version__
        manifest = {
            "opusbook": version, "python": sys.version, "glibc_minimum": "2.41",
            "pyinstaller": importlib.metadata.version("pyinstaller"),
            "ffmpeg": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0],
            "source_sha256": hashlib.sha256((ROOT / "opusbook.py").read_bytes()).hexdigest(),
        }
        (bundle / "BUILD.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        output = ROOT / "dist"
        output.mkdir(exist_ok=True)
        archive = Path(shutil.make_archive(str(output / f"opusbook-{version}-linux-x64"),
                                           "gztar", bundle.parent, bundle.name))
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_name(archive.name + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
        print(archive)


if __name__ == "__main__":
    main()
