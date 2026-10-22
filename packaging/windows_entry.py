"""Console entry point for the portable Windows distribution."""
import sys
from pathlib import Path

import opusbook


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    # Explicit options retain the regular CLI, including its exit codes.
    portable = not args or (len(args) == 1 and not args[0].startswith("-"))
    if not portable:
        return opusbook.main(args)

    polish = opusbook.detect_system_language() == "pl"
    code = 0
    try:
        if not args:
            print("Opusbook — folder lub plik audio" if polish else "Opusbook — audio file or folder")
            path = input("Wklej ścieżkę (Enter = wyjdź): " if polish else "Paste path (Enter = exit): ").strip()
            if not path:
                return 0
            args = [path.strip('"')]
        # An absolute path also protects names beginning with '-'.
        opusbook.main([str(Path(args[0]).resolve()), "-r", "--keep"])
    except EOFError:
        return 0
    except KeyboardInterrupt:
        code = 130
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
    finally:
        if sys.stdin.isatty() and sys.stdout.isatty():
            try:
                input("Enter, aby zamknąć…" if polish else "Press Enter to close…")
            except (EOFError, KeyboardInterrupt):
                pass
    return code


if __name__ == "__main__":
    sys.exit(main())
