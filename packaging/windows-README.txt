OPUSBOOK — WINDOWS PORTABLE (x64)

POLSKI
1. Rozpakuj CAŁY ZIP do zwykłego folderu. Nie uruchamiaj z wnętrza ZIP-a.
2. Przeciągnij JEDEN folder lub plik audio na opusbook.exe.
   Możesz też uruchomić opusbook.exe i wkleić pełną ścieżkę.
3. Wybierz jakość strzałkami i zatwierdź Enterem.
4. Wyniki .opus i ewentualna cover.jpg pojawią się obok źródeł.

Ten tryb uwzględnia podkatalogi i ZAWSZE zachowuje oryginały.
Istniejące pliki .opus są pomijane. Na końcu Enter zamyka okno.
Python, FFmpeg ani uprawnienia administratora nie są potrzebne.
Pozostaw ffmpeg.exe i ffprobe.exe obok opusbook.exe oraz folder _internal.

Pełna obsługa z PowerShella (przykład z zachowaniem źródeł):
  .\opusbook.exe "D:\Audiobooki" -r -b 64k --keep --lang pl
  .\opusbook.exe --help
Przy podaniu opcji działa zwykły interfejs CLI. --delete usuwa źródła.

ENGLISH
1. Extract the ENTIRE ZIP to a normal folder. Do not run inside the ZIP.
2. Drag ONE audio folder or file onto opusbook.exe, or double-click the
   executable and paste the full path.
3. Select the bitrate with arrow keys and press Enter.
4. Output .opus files and optional cover.jpg appear beside the sources.

This mode includes subfolders and ALWAYS keeps originals. Existing .opus
files are skipped. Press Enter at the end to close the window.
No Python, FFmpeg installation or administrator access is needed.
Keep ffmpeg.exe, ffprobe.exe and the _internal folder beside opusbook.exe.

PowerShell (explicit options use the regular CLI):
  .\opusbook.exe "D:\Audiobooks" -r -b 64k --keep --lang en
  .\opusbook.exe --help
--delete removes source files after successful validation.

https://github.com/patientone-io/opusbook
Opusbook: MIT (LICENSE). Bundled software: see third-party/.
