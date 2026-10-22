OPUSBOOK - LINUX PORTABLE (x86_64)

ENGLISH
Requires Linux x86_64 with glibc 2.41 or newer (not Alpine/musl).
Extract the entire archive, open a terminal in the opusbook folder and run:
  ./opusbook "/path/to/audiobooks" -r -b 64k --keep
  ./opusbook --help

Python, FFmpeg and ffprobe are included. Keep the entire folder together.
Outputs are written beside the sources. --keep preserves originals;
--delete removes them after successful validation. Existing outputs are
skipped unless you pass --force. No administrator access is needed.

POLSKI
Wymagany Linux x86_64 z glibc 2.41 lub nowszą (bez Alpine/musl).
Rozpakuj całe archiwum, otwórz terminal w folderze opusbook i uruchom:
  ./opusbook "/ścieżka/do/audiobooków" -r -b 64k --keep
  ./opusbook --help

Python, FFmpeg i ffprobe są dołączone. Zachowaj cały folder.
Wyniki powstają obok źródeł. --keep zachowuje oryginały;
--delete usuwa je po poprawnej walidacji. Istniejące wyniki są pomijane,
chyba że podasz --force. Uprawnienia administratora nie są potrzebne.

https://github.com/patientone-io/opusbook
Opusbook: MIT (LICENSE). Bundled software: see third-party/.
