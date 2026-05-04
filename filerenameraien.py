#!/usr/bin/env python3
"""
filerenameraien.py — Intelligent PDF renaming with a local AI model (Ollama)
=============================================================================

This script reads the text from PDF files, sends it to a locally running
Ollama language model, and lets it suggest a meaningful filename. The result
always follows the pattern:

    YYYY-MM-DD_DocumentType_Keyword1 Keyword2.pdf

Examples:
    2024-03-15_Invoice_Amazon OrderNo-12345 Item.pdf
    2023-11-01_Contract_Landlord GmbH LeaseAgreement Berlin.pdf
    2022-06-30_BankStatement_SampleBank CheckingAccount.pdf

How it works
------------
1.  All PDF files at the given path (or a single file) are discovered and
    processed in alphabetical order (case-insensitive).
2.  Up to ``--max-pages`` pages are read from each PDF and the text is
    truncated to ``--max-chars`` characters before being sent to the model.
    This guards against overly long prompts and keeps response times low.
3.  The Ollama model receives an English prompt and returns a JSON object
    with the fields ``date``, ``doc_type``, and ``keywords``.
4.  The returned values are sanitised (special characters removed) and
    assembled into a safe filename.
5.  Naming collisions are resolved automatically by appending a counter
    (-2, -3, …).
6.  In ``--dry-run`` mode only the suggested names are printed; no files
    are actually renamed.
7.  Files that cannot be opened (e.g. encrypted PDFs) are skipped; the
    remaining files continue to be processed.

Supported models
----------------
Tested with ``qwen3.5:latest`` (default) and ``llama3.2:latest``.
Reasoning models (which write JSON output to the ``thinking`` field instead
of ``response``) are detected and supported automatically.

Requirements
------------
- Python 3.10+
- pypdf >= 4.2 (``pip install pypdf``)
- Ollama running locally at http://127.0.0.1:11434
- The desired model downloaded with ``ollama pull <model>``

Usage
-----
    # Preview without renaming:
    python filerenameraien.py ~/Documents/Invoices --dry-run --recursive

    # Actual renaming:
    python filerenameraien.py ~/Documents/Invoices --recursive

    # Single file with a different model:
    python filerenameraien.py invoice.pdf --model llama3.2:latest

OCR fallback
------------
If a PDF contains no embedded text (e.g. scanned documents), the script
automatically tries to extract text via Tesseract OCR. This requires the
packages ``pytesseract`` and ``pdf2image`` as well as the system tools
``tesseract`` (with language pack ``eng``) and ``poppler``:

    brew install tesseract tesseract-lang poppler
    pip install pytesseract pdf2image

If these are missing the file is skipped.

Limitations
-----------
- The quality of the filename depends directly on the OCR text quality and
  the capability of the model used.
- All output is in English.

Author: Lars Eberhart
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib import error, request

from pypdf import PdfReader

# pytesseract and pdf2image are optional dependencies for the OCR fallback.
# If not installed, OCR is silently skipped.
try:
    import pytesseract
    from pdf2image import convert_from_path as _pdf2images

    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False


DEFAULT_MODEL = "qwen3.5:latest"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MAX_FILENAME_LENGTH = 120


def sanitize_date(value: str) -> str:
    """Returns value if it matches the YYYY-MM-DD format, otherwise '0000-00-00'."""
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    return "0000-00-00"


def sanitize_segment(value: str) -> str:
    """Keeps letters (incl. umlauts), digits, and hyphens; collapses whitespace into hyphens."""
    value = value.strip()
    value = re.sub(r"\s+", "-", value)
    value = re.sub(
        r"[^A-Za-z\u00c4\u00d6\u00dc\u00e4\u00f6\u00fc\u00df0-9-]", "", value
    )
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "Document"


def sanitize_keywords(value: str) -> str:
    """Processes a comma-separated keyword list and joins the cleaned parts with spaces."""
    parts = [p.strip() for p in value.split(",") if p.strip()]
    cleaned: list[str] = []
    for part in parts[:4]:
        part = re.sub(
            r"[^A-Za-z\u00c4\u00d6\u00dc\u00e4\u00f6\u00fc\u00df0-9 -]", "", part
        )
        part = re.sub(r" +", " ", part).strip()
        part = re.sub(r"-+", "-", part).strip("-")
        if part:
            cleaned.append(part)
    return " ".join(cleaned) or "unknown"


def build_filename(date: str, doc_type: str, keywords: str) -> str:
    name = f"{date}_{doc_type}_{keywords}"
    return name[:MAX_FILENAME_LENGTH].rstrip("_-") or "0000-00-00_Document_unknown"


@dataclass
class RenameResult:
    source: Path
    target: Path | None
    reason: str
    is_error: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rename PDF files based on their content using a local Ollama model."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="PDF file or directory. Default: current directory.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Name of the Ollama model. Default: {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--ollama-url",
        default=DEFAULT_OLLAMA_URL,
        help=f"Ollama generate endpoint. Default: {DEFAULT_OLLAMA_URL}.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively search subdirectories.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print suggested filenames without actually renaming files.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Maximum number of pages to read per PDF. Default: 5.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=6000,
        help="Maximum number of characters sent to the model. Default: 6000.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show additional diagnostic output.",
    )
    return parser.parse_args()


def discover_pdfs(path: Path, recursive: bool) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() == ".pdf" else []
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(
        (pdf for pdf in path.glob(pattern) if pdf.is_file()),
        key=lambda p: p.name.lower(),
    )


def _ocr_pdf(pdf_path: Path, max_pages: int, max_chars: int) -> str:
    """Converts PDF pages to images and extracts text via Tesseract OCR (English)."""
    if not _OCR_AVAILABLE:
        print("  [ocr] pytesseract/pdf2image not installed — OCR skipped.")
        print("  [ocr] Install with: pip install pytesseract pdf2image")
        print("  [ocr] System tools: brew install tesseract tesseract-lang poppler")
        return ""

    print(f"  [ocr] Starting Tesseract OCR (language: eng, max. {max_pages} pages) ...")
    try:
        # Render PDF pages as images (300 dpi for good OCR quality)
        images = _pdf2images(str(pdf_path), last_page=max_pages, dpi=300)
    except Exception as exc:
        print(f"  [ocr] Conversion failed: {exc}")
        return ""

    # Check available Tesseract languages; fall back to English
    try:
        available_langs = pytesseract.get_languages()
        lang = "eng" if "eng" in available_langs else "deu"
        if lang != "eng":
            print(
                "  [ocr] Warning: Tesseract language pack 'eng' not found, using 'deu'."
            )
            print("  [ocr] Install with: brew install tesseract-lang")
    except Exception:
        lang = "eng"

    snippets: list[str] = []
    total_chars = 0
    for i, image in enumerate(images, start=1):
        try:
            raw = pytesseract.image_to_string(image, lang=lang)
        except Exception as exc:
            print(f"  [ocr] Page {i}: Tesseract error: {exc}")
            continue
        cleaned = " ".join(raw.split())
        print(f"  [ocr] Page {i}: {len(cleaned)} characters recognised")
        if cleaned:
            snippets.append(cleaned)
            total_chars += len(cleaned)
        if total_chars >= max_chars:
            print(f"  [ocr] max_chars limit ({max_chars}) reached, stopping")
            break

    result = "\n".join(snippets)[:max_chars].strip()
    print(f"  [ocr] OCR extraction complete: {len(result)} characters total")
    return result


def extract_pdf_text(
    pdf_path: Path, max_pages: int, max_chars: int, verbose: bool = False
) -> str:
    print(f"  [extract] Opening PDF: {pdf_path.name}")
    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        print(f"  [extract] Cannot open PDF: {exc}")
        return ""
    total_pages = len(reader.pages)
    print(f"  [extract] Total pages: {total_pages} (reading up to {max_pages})")
    snippets: list[str] = []
    total_chars = 0
    for i, page in enumerate(reader.pages[:max_pages], start=1):
        text = page.extract_text() or ""
        cleaned = " ".join(text.split())
        print(f"  [extract] Page {i}: {len(cleaned)} characters")
        if cleaned:
            snippets.append(cleaned)
            total_chars += len(cleaned)
        if total_chars >= max_chars:
            print(f"  [extract] max_chars limit ({max_chars}) reached, stopping")
            break
    joined = "\n".join(snippets)
    result = joined[:max_chars].strip()
    print(f"  [extract] Total extracted: {len(result)} characters")
    if verbose and result:
        print(f"  [extract] Text preview: {result[:300]!r}...")

    # No embedded text found — try OCR fallback via Tesseract
    if not result:
        print("  [extract] No embedded text found, trying OCR fallback ...")
        result = _ocr_pdf(pdf_path, max_pages=max_pages, max_chars=max_chars)
        if verbose and result:
            print(f"  [ocr] Text preview: {result[:300]!r}...")

    return result


def build_prompt(file_name: str, extracted_text: str) -> str:
    return (
        "You are an assistant that renames PDF files based on their content.\n"
        "Analyse the following PDF text and return exclusively a valid JSON object "
        "with exactly these three keys:\n"
        '  "date": The date of the document (invoice date, contract date, receipt date, etc.) '
        'in the format YYYY-MM-DD. If no date is found, use "0000-00-00".\n'
        '  "doc_type": The document type in English, exactly one word '
        "(e.g. Invoice, Contract, Statement, Order, BankStatement, DeliveryNote, "
        "Reminder, Receipt, PaySlip).\n"
        '  "keywords": Comma-separated list of two to four keywords (separated by spaces in the filename). '
        "The order must be strictly followed: "
        "1. Sender of the document (company, authority, or person who issued it) — mandatory. "
        "2. Order number, invoice number, or another unique identifier, if available. "
        "3. Product, service, contract number, or main topic of the document. "
        "4. One further keyword that clarifies the context (e.g. plan name, location, item description). "
        "Never include the recipient of the document as a keyword. "
        "Never use the word 'ShippingCosts' as a keyword. "
        "Preserve spaces within a keyword (do not replace with hyphens), "
        "only ASCII letters, digits, spaces, and hyphens are allowed — remove all other special characters.\n"
        "No further explanations, only the JSON object.\n\n"
        f"Filename: {file_name}\n"
        "Extracted PDF text:\n"
        f"{extracted_text}\n"
    )


def request_filename_from_ollama(
    *,
    pdf_path: Path,
    extracted_text: str,
    model: str,
    ollama_url: str,
    verbose: bool = False,
) -> str:
    print(f"  [ollama] Sending request to {ollama_url} with model '{model}'")
    payload = {
        "model": model,
        "prompt": build_prompt(pdf_path.name, extracted_text),
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.2,
        },
    }
    encoded = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        ollama_url,
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        print("  [ollama] Waiting for response...")
        with request.urlopen(http_request, timeout=180) as response:
            body = response.read().decode("utf-8")
        print(f"  [ollama] Response received ({len(body)} bytes)")
    except error.URLError as exc:
        raise RuntimeError(f"Ollama not reachable at {ollama_url}: {exc}") from exc

    if verbose:
        print(f"  [ollama] Raw response: {body[:1000]}")

    try:
        outer = json.loads(body)
        raw = outer.get("response") or outer.get("thinking", "")
        if not raw:
            raise RuntimeError(
                f"Fields 'response' and 'thinking' are both empty for {pdf_path.name}: {body}"
            )
        if raw != outer.get("response"):
            print(f"  [ollama] 'response' was empty, using 'thinking' field")
        inner = json.loads(raw)
        print(f"  [ollama] Parsed JSON: {inner}")
        date = sanitize_date(inner.get("date", "0000-00-00"))
        doc_type = sanitize_segment(inner.get("doc_type", "Document"))
        keywords = sanitize_keywords(inner.get("keywords", "unknown"))
        print(f"  [ollama] date={date!r}, doc_type={doc_type!r}, keywords={keywords!r}")
    except (KeyError, json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(
            f"Unexpected response from Ollama for {pdf_path.name}: {body}"
        ) from exc

    filename = build_filename(date, doc_type, keywords)
    print(f"  [ollama] Suggested filename: {filename!r}")
    return filename


def ensure_unique_path(target: Path) -> Path:
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    counter = 2
    while True:
        candidate = target.with_name(f"{stem}-{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def rename_pdf(
    pdf_path: Path,
    *,
    model: str,
    ollama_url: str,
    dry_run: bool,
    max_pages: int,
    max_chars: int,
    verbose: bool = False,
) -> RenameResult:
    print(f"\n--- Processing: {pdf_path.name} ---")
    extracted_text = extract_pdf_text(
        pdf_path, max_pages=max_pages, max_chars=max_chars, verbose=verbose
    )
    if not extracted_text:
        print("  [skip] No extractable text found")
        return RenameResult(source=pdf_path, target=None, reason="no extractable text")

    suggested_name = request_filename_from_ollama(
        pdf_path=pdf_path,
        extracted_text=extracted_text,
        model=model,
        ollama_url=ollama_url,
        verbose=verbose,
    )
    target_path = pdf_path.with_name(f"{suggested_name}.pdf")

    if target_path == pdf_path:
        print("  [skip] File already has the suggested name")
        return RenameResult(
            source=pdf_path, target=pdf_path, reason="already correctly named"
        )

    target = ensure_unique_path(target_path)

    if not dry_run:
        print(f"  [rename] {pdf_path.name} -> {target.name}")
        pdf_path.rename(target)
    else:
        print(f"  [dry-run] Would rename: {pdf_path.name} -> {target.name}")
    return RenameResult(
        source=pdf_path, target=target, reason="renamed" if not dry_run else "dry-run"
    )


def iter_results(args: argparse.Namespace) -> Iterable[RenameResult]:
    source_path = Path(args.path).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Path does not exist: {source_path}")

    pdf_files = discover_pdfs(source_path, recursive=args.recursive)
    if not pdf_files:
        raise FileNotFoundError(f"No PDF files found under: {source_path}")

    print(f"[info] {len(pdf_files)} PDF(s) found in {source_path}")
    print(f"[info] Model: {args.model}")
    print(f"[info] Ollama URL: {args.ollama_url}")
    print(f"[info] Dry-run: {args.dry_run}")
    for i, pdf_path in enumerate(pdf_files, start=1):
        print(f"\n[{i}/{len(pdf_files)}] {pdf_path.name}")
        try:
            yield rename_pdf(
                pdf_path,
                model=args.model,
                ollama_url=args.ollama_url,
                dry_run=args.dry_run,
                max_pages=args.max_pages,
                max_chars=args.max_chars,
                verbose=args.verbose,
            )
        except Exception as exc:
            print(f"  [error] {pdf_path.name}: {exc}")
            yield RenameResult(source=pdf_path, target=None, reason=str(exc), is_error=True)


def main() -> int:
    args = parse_args()
    failures = 0

    try:
        for result in iter_results(args):
            if result.target is None:
                failures += 1
                if result.is_error:
                    print(f"ERROR         {result.source.name}: {result.reason}")
                else:
                    print(f"SKIPPED       {result.source.name}: {result.reason}")
                continue

            if args.verbose:
                print(f"INFO  {result.source} -> {result.target}")
            else:
                print(
                    f"OK    {result.source.name} -> {result.target.name} ({result.reason})"
                )
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
