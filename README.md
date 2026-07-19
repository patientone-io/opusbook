# 🎵 opusbook

> 🎧 Fast, multi-threaded audio-to-Opus converter for audiobooks and podcasts. Saves 60–75% disk space with pristine voice quality.
>
> 🇵🇱 Szybki, wielowątkowy konwerter audio do formatu Opus dla audiobooków i podcastów. Oszczędza 60–75% miejsca na dysku przy zachowaniu krystalicznej jakości mowy.

[ 🇬🇧 English ](#-english) • [ 🇵🇱 Polski ](#-polski)

---

## 🇬🇧 English

A command-line tool that converts audio files (**MP3, M4B, M4A, FLAC, AAC, WAV, OGG, WMA**) into **Opus**. Tailored for audiobooks, podcasts, and radio plays to achieve substantial storage savings (typically 60–75% size reduction) without perceptible loss in speech quality.

Features a colorful terminal interface (`rich`), interactive bitrate selection, multi-core batch processing, and automatic channel optimization.

![Multi-threaded encoding progress](assets/demo-progress-en.png)

![Conversion results and summary](assets/demo-summary-en.png)

### 🌟 Key Features

- 🎧 **Broad format support:** Converts `.mp3`, `.m4b`, `.m4a`, `.flac`, `.aac`, `.wav`, `.ogg`, `.wma` to `.opus` using `ffmpeg` (`libopus`, VBR, `-application audio`).
- 🎯 **Interactive bitrate picker:** Terminal menu with arrow navigation (48k / 64k / 80k) or quick CLI flag (`-b 64k`).
- 🧠 **Smart `--auto` mode:** Detects channels automatically (mono → 32k, stereo → selected bitrate).
- 📁 **Recursive scanning (`-r`):** Traverses deep audiobook folder hierarchies.
- ⚡ **Multi-threading (`-j N`):** Parallel transcoding with individual and aggregate progress bars (`rich`).
- 🖼️ **Cover art extraction:** Extracts embedded covers to `cover.jpg` (sidecar) for Audiobookshelf and media players.
- 📊 **Summary table:** Reports saved megabytes, size reduction percentage, and encoding speed.
- 🛡️ **Safety & cleanup:** `--delete` (removes source files only after successful conversion), `--keep`, `--force`, `--dry-run`.
- 🤖 **Non-TTY resilient:** Automatic fallback to clean batch output (ideal for cron jobs and headless scripts).

### 🚀 Installation

**Requirements:** Python 3.9+ and `ffmpeg` installed on your system.

#### Global CLI via `pipx` or `uv` (Recommended)

```bash
pipx install git+https://github.com/patientone-io/opusbook.git
# or with uv:
uv tool install git+https://github.com/patientone-io/opusbook.git
```

#### From source in a virtualenv

```bash
git clone https://github.com/patientone-io/opusbook.git
cd opusbook
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

### 💡 Usage Examples

```bash
# 1. Convert current directory with default 64k bitrate
opusbook .

# 2. Recursive conversion with 80k bitrate (for audio plays with music/SFX)
opusbook audiobooks/ -r -b 80k

# 3. Auto-bitrate (mono 32k, stereo 64k) and remove source files upon success
opusbook audiobooks/ -r --auto --delete

# 4. Dry run: preview planned ffmpeg commands without encoding
opusbook audiobooks/ -r --dry-run
```

### ⚙️ CLI Options

| Argument | Description | Default |
| :--- | :--- | :--- |
| `PATH` | Path to directory containing audio files | `.` |
| `-b, --bitrate` | Target Opus bitrate (`48k`, `64k`, `80k`, etc.) | Interactive / `64k` |
| `-j, --jobs` | Number of concurrent ffmpeg worker processes | `min(4, CPU cores)` |
| `-r, --recurse` | Recursively search subdirectories | `False` |
| `--auto` | Auto-optimize bitrate (mono → 32k, stereo → from `-b`) | `False` |
| `-f, --force` | Overwrite existing `.opus` files | `False` |
| `--delete` | Delete input files after successful conversion | `False` |
| `--keep` | Keep input files (skip interactive confirmation) | `True` |
| `--dry-run` | Display scheduled ffmpeg commands without executing | `False` |
| `-l, --lang` | Interface language (`auto`, `en`, `pl`) | `auto` (system locale) |

---

## 🇵🇱 Polski

Narzędzie wiersza poleceń do konwersji plików audio **(MP3, M4B, M4A, FLAC, AAC, WAV, OGG, WMA) → Opus**. Zaprojektowane specjalnie z myślą o audiobookach, słuchowiskach i podcastach, zapewniające ogromną oszczędność miejsca (zazwyczaj 60–75% mniejszy rozmiar) przy zachowaniu doskonałej jakości mowy.

Oferuje kolorowy interfejs terminalowy (`rich`), interaktywny wybór bitrate'a, wielowątkowe przetwarzanie oraz automatyczną optymalizację kanałów (mono/stereo).

![Przebieg wielowątkowej konwersji](assets/demo-progress-pl.png)

![Tabela wyników i zaoszczędzone miejsce](assets/demo-summary-pl.png)

### 🌟 Główne Funkcje

- 🎧 **Wsparcie dla wielu formatów:** Konwertuje `.mp3`, `.m4b`, `.m4a`, `.flac`, `.aac`, `.wav`, `.ogg`, `.wma` do formatu `.opus` przez `ffmpeg` (`libopus`, VBR, `-application audio`).
- 🎯 **Interaktywny wybór bitrate'a:** Wygodne menu w terminalu (48k / 64k / 80k) lub przełącznik `-b 64k`.
- 🧠 **Inteligentny tryb `--auto`:** Automatyczne rozpoznawanie kanałów (mono → 32k, stereo → wybrany bitrate).
- 📁 **Rekurencyjne skanowanie (`-r`):** Przeszukuje całe drzewa folderów z audiobookami.
- ⚡ **Wielowątkowość (`-j N`):** Równoległa konwersja z indywidualnymi i łącznymi paskami postępu (`rich`).
- 🖼️ **Ekstrakcja okładek:** Zapis osadzonych grafik do `cover.jpg` (sidecar) dla Audiobookshelf i odtwarzaczy.
- 📊 **Tabela podsumowania:** Prezentuje zaoszczędzone MB, procent redukcji i prędkość kodowania.
- 🛡️ **Opcje czyszczenia:** `--delete` (usuwa pliki źródłowe po udanej konwersji), `--keep`, `--force`, `--dry-run`.
- 🤖 **Odporność na brak TTY:** Automatyczny fallback do trybu wsadowego (skrypty cron i CI).

### 🚀 Instalacja

**Wymagania:** Python 3.9+ oraz zainstalowany w systemie `ffmpeg`.

#### Globalne CLI przez `pipx` lub `uv` (Zalecane)

```bash
pipx install git+https://github.com/patientone-io/opusbook.git
# lub za pomocą uv:
uv tool install git+https://github.com/patientone-io/opusbook.git
```

#### Ze źródeł w wirtualnym środowisku

```bash
git clone https://github.com/patientone-io/opusbook.git
cd opusbook
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

### 💡 Przykłady Użycia

```bash
# 1. Konwersja w bieżącym folderze (domyślny bitrate 64k)
opusbook .

# 2. Rekurencyjna konwersja słuchowiska z bitratem 80k
opusbook sluchowisko/ -r -b 80k

# 3. Auto-bitrate (mono 32k, stereo 64k) z usunięciem plików źródłowych
opusbook audiobook/ -r --auto --delete

# 4. Tryb symulacji (podgląd planowanych komend ffmpeg bez uruchamiania)
opusbook audiobook/ -r --dry-run
```

### ⚙️ Parametry CLI

| Argument | Opis | Domyślnie |
| :--- | :--- | :--- |
| `ŚCIEŻKA` | Ścieżka do katalogu z plikami audio | `.` |
| `-b, --bitrate` | Bitrate wyjściowy (`48k`, `64k`, `80k` itp.) | Interaktywny / `64k` |
| `-j, --jobs` | Liczba równoległych procesów ffmpeg | `min(4, rdzenie CPU)` |
| `-r, --recurse` | Rekurencyjne przeszukiwanie podkatalogów | `False` |
| `--auto` | Auto-optymalizacja (mono → 32k, stereo → z `-b`) | `False` |
| `-f, --force` | Nadpisywanie istniejących plików `.opus` | `False` |
| `--delete` | Usunięcie plików wejściowych po udanej konwersji | `False` |
| `--keep` | Zachowanie plików wejściowych bez pytania | `True` |
| `--dry-run` | Tryb symulacji: wyświetlenie zaplanowanych komend bez konwersji | `False` |
| `-l, --lang` | Język interfejsu (`auto`, `pl`, `en`) | `auto` (zmienna systemowa) |

---

## 👤 Author & Contact / Autor i kontakt

- **Author:** [patientone](https://github.com/patientone-io)
- **Website:** [patientone.uk](https://patientone.uk)
- **Email:** `contact@patientone.uk`

---

## 📄 License / Licencja

- **EN:** Released under the **MIT License**. See [LICENSE](LICENSE) for details.
- **PL:** Projekt udostępniany na licencji **MIT**. Szczegóły w pliku [LICENSE](LICENSE).

