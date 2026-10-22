"""Exercise an extracted portable archive with an empty PATH."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", nargs="?", help="Path to extracted opusbook executable")
    args = parser.parse_args()
    suffix = ".exe" if os.name == "nt" else ""
    candidate = args.executable or shutil.which("opusbook" + suffix)
    if not candidate:
        raise SystemExit("Pass the extracted executable path.")
    executable = Path(candidate).resolve()
    ffmpeg = executable.with_name("ffmpeg" + suffix)
    ffprobe = executable.with_name("ffprobe" + suffix)
    environment = dict(os.environ, PATH="", OPUSBOOK_LANG="en")

    def run(*args, **kwargs):
        try:
            return subprocess.run(
                [str(arg) for arg in args], check=True, capture_output=True,
                encoding="utf-8", errors="replace", env=environment, timeout=90, **kwargs,
            )
        except subprocess.CalledProcessError as error:
            print(error.stdout)
            print(error.stderr)
            raise

    run(executable, "--help")
    run(executable, "--version")
    # Empty input cancels the double-click wizard instead of converting CWD.
    if os.name == "nt":
        run(executable, input="\n")
    with tempfile.TemporaryDirectory(prefix="opusbook smoke żółć ") as directory:
        root = Path(directory)
        folder = root / "Książka [test]" / "Podfolder"
        folder.mkdir(parents=True)
        source = folder / "Rozdział ąę.wav"
        run(ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", source)
        original = source.read_bytes()
        image = root / "embedded.jpg"
        run(ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=32x32",
            "-frames:v", "1", "-update", "1", image)
        covered = folder / "Okładka.mp3"
        run(ffmpeg, "-v", "error", "-i", source, "-i", image, "-map", "0:a", "-map", "1:v",
            "-c:a", "libmp3lame", "-c:v", "copy", "-id3v2_version", "3",
            "-disposition:v", "attached_pic", covered)
        covered_original = covered.read_bytes()
        # Windows drop mode keeps recursively; Linux uses explicit CLI options.
        options = [] if os.name == "nt" else ["-r", "--keep", "-b", "64k"]
        run(executable, folder.parent, *options, input="")
        output = source.with_suffix(".opus")
        assert source.read_bytes() == original
        assert covered.read_bytes() == covered_original
        cover = folder / "cover.jpg"
        assert cover.is_file()
        run(ffmpeg, "-v", "error", "-xerror", "-i", cover, "-f", "null", "-")
        metadata = json.loads(run(
            ffprobe, "-v", "error", "-show_streams", "-of", "json", output,
        ).stdout)
        assert metadata["streams"][0]["codec_name"] == "opus"
        previous = output.read_bytes()
        run(executable, folder.parent, *options, input="")
        assert output.read_bytes() == previous
        assert source.read_bytes() == original
        # Exercise actual filesystem replacement and validated deletion.
        run(executable, source, "--force", "--delete", "-b", "48k")
        assert not source.exists() and output.is_file()
        run(executable, covered, "--force", "--delete", "-b", "64k")
        assert not covered.exists() and covered.with_suffix(".opus").is_file() and cover.is_file()
        assert not list(folder.glob(".opusbook.*.opus"))
        invalid = folder / "Broken.wav"
        invalid.write_bytes(b"invalid audio")
        failed = subprocess.run(
            [str(executable), str(invalid), "--delete", "-b", "64k"],
            env=environment, capture_output=True, timeout=90,
        )
        assert failed.returncode == 1 and invalid.exists()
        assert not invalid.with_suffix(".opus").exists()
    print("Extracted archive smoke passed (PATH empty, Unicode paths, recursive keep, skip, force/delete, failure).")


if __name__ == "__main__":
    main()
