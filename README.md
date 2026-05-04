# FileRenamer_AI_EN

Intelligent PDF renaming using a locally running AI model (Ollama).

The script reads the embedded text from PDF files, sends it to a local
Ollama language model, and renames the file according to a consistent,
human-readable scheme:

```
YYYY-MM-DD_DocumentType_Sender Keyword2 Keyword3.pdf
```

**Examples:**
```
2024-03-15_Invoice_Amazon Order-12345.pdf
2023-11-01_Contract_Wiener Wohnen Lease Vienna.pdf
2022-06-30_BankStatement_Trottelbank CheckingAccount March.pdf
2017-04-26_Invoice_T-Mobile Invoice SIM.pdf
```

---

## Requirements

- **Python 3.10** or newer
- **Ollama** installed locally and running (`ollama serve`)
- A downloaded Ollama model (tested with `qwen3.5:latest` and `llama3.2:latest`)
- Text-based PDFs are supported directly. For **scanned PDFs without embedded text**, the script automatically falls back to Tesseract OCR (optional installation, see below)

---

## Installation

> **Tip:** If you prefer not to set things up manually, you can use the included setup script, it handles all of the following steps automatically.

---

## Automatic Setup with `setup.sh`

Instead of installing each prerequisite by hand, the included `setup.sh`
script can handle the entire setup. It checks each step, asks for
confirmation before each installation, and continuously reports what it is doing.

### What the script sets up

The script performs the following actions, with confirmation before each step:

| Step | Action |
|---|---|
| 1 | Check and install **Homebrew** if needed (required for all subsequent steps) |
| 2 | Check and install **Python 3.10+** via Homebrew if needed |
| 3 | Check and install **Tesseract OCR**, the German language pack (`deu`), and **Poppler** if needed (optional, for scanned PDFs) |
| 4 | Check and install **Ollama** if needed and download the default model `qwen3.5:latest` |
| 5 | Create the **`.venv`** virtual Python environment (or recreate it on request) |
| 6 | Install all **Python packages** from `requirements.txt` into the venv |
| 7 | **Activate** the virtual environment in the current shell session |
| 8 | Start **Ollama** in the background (`ollama serve`) if not already running |

Already installed components are automatically detected and skipped; nothing will be installed twice.

### Prerequisites

- macOS (the script uses Homebrew as its package manager)
- An active internet connection (for installing missing packages)

### Usage

```bash
# One-time: make the script executable
chmod +x setup.sh

# Run the script
./setup.sh
```

The script walks through all steps and asks for confirmation (`y` for yes,
`n` / Enter for no) before each installation. To skip a step, simply answer
`n`: all remaining steps will still be offered.

### Note on venv activation

When the script is run as `./setup.sh`, it runs in a subshell.
The venv activation in step 7 therefore only applies for the duration of
the script itself. To permanently activate the venv in your own shell
session, run once after setup:

```bash
source .venv/bin/activate
```

---

## Manual Installation

### 1. Clone the repository or download the files

```bash
git clone <repository-url>
cd FileRenamer
```

### 2. Create and activate a virtual Python environment

A virtual environment isolates installed packages from the system Python
and prevents conflicts with other projects.

```bash
# Create the virtual environment (once)
python3 -m venv .venv

# Activate (macOS / Linux)
source .venv/bin/activate

```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

This installs all packages including the optional OCR dependencies
`pytesseract`, `pdf2image`, and `Pillow`.

### 4. Install Tesseract (for scanned PDFs, recommended)

For PDFs without embedded text (scanned documents), Tesseract OCR is used
as an automatic fallback. Two system tools are required:

```bash
# macOS (via Homebrew)
brew install tesseract tesseract-lang poppler
```

| Tool | Purpose |
|---|---|
| `tesseract` | OCR engine |
| `tesseract-lang` | Language packs, incl. German (`deu`) |
| `poppler` | PDF-to-image conversion for `pdf2image` |

If Tesseract is not installed, scanned PDFs are automatically skipped
and a notice is displayed; everything else continues to work normally.

### 5. Download an Ollama model

```bash
# Recommended model (default):
ollama pull qwen3.5:latest

# Alternative, smaller model:
ollama pull llama3.2:latest
```

### 6. Start Ollama (if not already running)

```bash
ollama serve
```

Ollama runs by default at `http://127.0.0.1:11434`. The script
uses this endpoint automatically.

---

## Usage

### Activate the virtual environment (each new terminal session)

```bash
source .venv/bin/activate
```

### Preview without renaming (recommended for testing)

```bash
python filerenamerkide.py ~/Documents/Invoices --dry-run
```

With `--dry-run`, the suggested filenames are only displayed
without actually renaming any files.

### Rename files

```bash
python filerenamerkide.py ~/Documents/Invoices
```

### Process subfolders recursively

```bash
python filerenamerkide.py ~/Documents --recursive
```

### Rename a single file

```bash
python filerenamerkide.py ~/Desktop/invoice.pdf
```

### Use a different model

```bash
python filerenamerkide.py ~/Documents/Invoices --model llama3.2:latest
```

### Verbose diagnostic output

```bash
python filerenamerkide.py ~/Documents/Invoices --verbose
```

With `--verbose`, the raw Ollama response and a text preview of the
PDF extraction are also printed, which is useful for troubleshooting.

---

## All Options at a Glance

| Option | Default | Description |
|---|---|---|
| `path` | `.` (current directory) | PDF file or directory to process |
| `--model` | `qwen3.5:latest` | Name of the Ollama model |
| `--ollama-url` | `http://127.0.0.1:11434/api/generate` | URL of the Ollama endpoint |
| `--recursive` | off | Search subfolders recursively |
| `--dry-run` | off | Preview only, no renaming |
| `--max-pages` | `5` | Maximum number of pages to read per PDF |
| `--max-chars` | `6000` | Maximum number of characters sent to the model |
| `--verbose` | off | Show additional diagnostic output |

---

## Output Format

The script prints a detailed status line for each file:

```
[info] 3 PDF(s) found in /Users/.../Invoices
[info] Model: qwen3.5:latest
[info] Ollama URL: http://127.0.0.1:11434/api/generate
[info] Dry-run: False

[1/3] invoice_april.pdf

--- Processing: invoice_april.pdf ---
  [extract] Opening PDF: invoice_april.pdf
  [extract] Total pages: 2 (reading up to 5)
  [extract] Page 1: 1842 characters
  [extract] Page 2: 634 characters
  [extract] Total extracted: 2476 characters
  [ollama] Sending request to http://127.0.0.1:11434/api/generate with model 'qwen3.5:latest'
  [ollama] Waiting for response...
  [ollama] Response received (512 bytes)
  [ollama] Parsed JSON: {'date': '2024-04-01', 'doc_type': 'Invoice', 'keywords': 'Amazon, Order-12345, Kindle'}
  [ollama] date='2024-04-01', doc_type='Invoice', keywords='Amazon Order-12345 Kindle'
  [ollama] Suggested filename: '2024-04-01_Invoice_Amazon Order-12345 Kindle'
  [rename] invoice_april.pdf -> 2024-04-01_Invoice_Amazon Order-12345 Kindle.pdf
OK    invoice_april.pdf -> 2024-04-01_Invoice_Amazon Order-12345 Kindle.pdf (renamed)
```

**Status lines at the end:**
- `OK`: File successfully renamed
- `SKIPPED`: File skipped (no extractable text)
- `ERROR`: Error during processing (e.g. Ollama not reachable)

**Exit codes:**
- `0`: All files processed successfully
- `1`: Fatal error (Ollama not reachable, path not found)
- `2`: At least one file was skipped

---

## How It Works

1. **PDF detection:** The script finds all `.pdf` files at the given path (optionally recursive).
2. **Text extraction:** `pypdf` extracts the embedded text page by page, limited to `--max-chars` characters.
3. **OCR fallback:** If the PDF contains no embedded text (e.g. scanned documents), pages are automatically converted to images using `pdf2image` and read with Tesseract OCR (language: German). If the German language pack is not installed, English is used as a fallback. If `pytesseract` or `pdf2image` are missing entirely, the file is skipped.
4. **AI analysis:** The text is sent to Ollama along with a prompt. The model returns a JSON object containing:
   - `date`: Document date in `YYYY-MM-DD` format
   - `doc_type`: Document type (Invoice, Contract, BankStatement, ...)
   - `keywords`: 2-4 keywords in a defined order: sender, identifier, topic, detail
5. **Sanitization:** Special characters are removed; spaces within a keyword are preserved.
6. **Collision avoidance:** If the target filename already exists, `-2`, `-3`, etc. are appended automatically.
7. **Renaming:** The file is renamed in place within the same folder.

---

## Notes and Limitations

- **Scanned PDFs:** These are automatically processed via Tesseract OCR if `pytesseract`, `pdf2image`, and the Tesseract system tool are installed. If any of these are missing, the file is skipped.
- **OCR quality:** Tesseract's recognition accuracy depends on scan quality. Very poor scans (low resolution, handwriting) may result in inaccurate naming.
- **Naming quality:** Directly depends on the model used and the quality of the extracted text. Larger models generally produce better results.
- **Reasoning models** (e.g. `qwen3.5`) that return their answer in the `thinking` field instead of the `response` field are automatically detected and supported.
- **No internet connection required:** The entire model and OCR run locally on your own machine.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `pypdf` | ≥ 4.2, < 6.0 | Text extraction from text-based PDF files |
| `pytesseract` | ≥ 0.3.10 | Python wrapper for Tesseract OCR (OCR fallback) |
| `pdf2image` | ≥ 1.17.0 | Conversion of PDF pages to images for OCR |
| `Pillow` | ≥ 10.0.0 | Image processing (dependency of pdf2image) |

The OCR fallback additionally requires the following **system tools** (not installable via pip):

| Tool | Installation (macOS) | Purpose |
|---|---|---|
| `tesseract` | `brew install tesseract` | OCR engine |
| Language pack `deu` | `brew install tesseract-lang` | German Tesseract model |
| `poppler` | `brew install poppler` | PDF rendering for pdf2image |

All other modules used (`argparse`, `json`, `re`, `urllib`, …) are part of the Python standard library.

---

*Author: Lars Eberhart*
