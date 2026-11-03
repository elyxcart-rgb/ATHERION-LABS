"""SONIC AI — Universal Content Extractor.

A high-end content extraction layer that pulls **text + metadata** out
of the most common file types — PDF, DOCX, XLSX, PPTX, CSV, JSON, XML,
HTML, images (via OCR when available), and source code.

Why this matters:
    - Existing ``actions.file_processor`` is action-call focused.
    - This module is **library-grade**: pure functions, no side effects,
      uniform return type (``ExtractedDocument``), easy to embed.

Public surface (stable, opt-in):
    - ``ContentExtractor``           — main class
    - ``ExtractedDocument``          — dataclass
    - ``extract(path)``              — dispatch by extension
    - ``extract_pdf(path)``, ``extract_docx(path)``, …

Zero-touch design: no existing file is modified.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import mimetypes
import re
import tokenize
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("CONTENT")

_MAX_BYTES = 50 * 1024 * 1024  # 50 MB hard cap per file


# ═════════════════════════════════════════════════════════════════════════════
# Data class
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class ExtractedDocument:
    path: str
    kind: str                    # pdf | docx | xlsx | pptx | csv | json | xml | html | code | text | image
    text: str = ""
    metadata: dict = field(default_factory=dict)
    pages: int = 0
    tables: list = field(default_factory=list)   # list[list[list[str]]]
    images: list = field(default_factory=list)   # list[dict] with keys: index, format, size
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    bytes_read: int = 0

    @property
    def ok(self) -> bool:
        return not self.error

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "kind": self.kind,
            "preview": self.text[:500],
            "full_length": len(self.text),
            "pages": self.pages,
            "tables_count": len(self.tables),
            "images_count": len(self.images),
            "metadata": self.metadata,
            "error": self.error,
            "warnings": self.warnings,
        }


# ═════════════════════════════════════════════════════════════════════════════
# Helper: safe binary read
# ═════════════════════════════════════════════════════════════════════════════

def _safe_read_bytes(path: Path, max_bytes: int = _MAX_BYTES) -> bytes:
    with open(path, "rb") as f:
        data = f.read(max_bytes + 1)
    return data[:max_bytes]


# ═════════════════════════════════════════════════════════════════════════════
# PDF
# ═════════════════════════════════════════════════════════════════════════════

def _extract_pdf(path: Path) -> ExtractedDocument:
    """Extract text + metadata from a PDF. Uses pypdf (already a dep) or
    PyPDF2 / pdfplumber if installed."""
    doc = ExtractedDocument(path=str(path), kind="pdf")
    try:
        data = _safe_read_bytes(path)
        doc.bytes_read = len(data)

        # Prefer pdfplumber (best table extraction) → pypdf → PyPDF2
        try:
            import pdfplumber  # type: ignore
            has_pdfplumber = True
        except ImportError:
            has_pdfplumber = False
        try:
            import pypdf  # type: ignore
            has_pypdf = True
        except ImportError:
            has_pypdf = False

        if has_pypdf:
            reader = pypdf.PdfReader(io.BytesIO(data))
            doc.metadata = {k: str(v) for k, v in (reader.metadata or {}).items()}
            doc.pages = len(reader.pages)
            texts = []
            for i, page in enumerate(reader.pages):
                try:
                    t = page.extract_text() or ""
                except Exception as e:
                    doc.warnings.append(f"Page {i}: {e}")
                    t = ""
                texts.append(t)
            doc.text = "\n\n".join(texts)

        if has_pdfplumber and not doc.text.strip():
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                doc.metadata = {k: str(v) for k, v in (pdf.metadata or {}).items()}
                doc.pages = len(pdf.pages)
                texts = []
                tables = []
                for page in pdf.pages:
                    texts.append(page.extract_text() or "")
                    try:
                        for tbl in page.extract_tables() or []:
                            tables.append([[(c or "").strip() for c in row]
                                           for row in tbl])
                    except Exception:
                        continue
                doc.text = "\n\n".join(texts)
                doc.tables = tables

        if not has_pypdf and not has_pdfplumber:
            doc.error = "Install pypdf or pdfplumber for PDF extraction"
    except Exception as e:
        doc.error = f"PDF extraction failed: {e}"
    return doc


# ═════════════════════════════════════════════════════════════════════════════
# DOCX
# ═════════════════════════════════════════════════════════════════════════════

def _extract_docx(path: Path) -> ExtractedDocument:
    doc = ExtractedDocument(path=str(path), kind="docx")
    try:
        from docx import Document  # python-docx
        data = _safe_read_bytes(path)
        doc.bytes_read = len(data)
        d = Document(io.BytesIO(data))
        core = d.core_properties
        doc.metadata = {
            "title": core.title or "",
            "author": core.author or "",
            "subject": core.subject or "",
            "created": str(core.created) if core.created else "",
            "modified": str(core.modified) if core.modified else "",
            "paragraphs": len(d.paragraphs),
            "tables": len(d.tables),
        }
        texts = [p.text for p in d.paragraphs if p.text]
        # Add table text
        for tbl in d.tables:
            for row in tbl.rows:
                row_text = " | ".join(c.text.strip() for c in row.cells)
                if row_text.strip(" |"):
                    texts.append(row_text)
        doc.text = "\n".join(texts)
        # Embed table summaries
        doc.tables = [
            [[c.text.strip() for c in row.cells] for row in t.rows]
            for t in d.tables
        ]
    except ImportError:
        doc.error = "Install python-docx for DOCX extraction"
    except Exception as e:
        doc.error = f"DOCX extraction failed: {e}"
    return doc


# ═════════════════════════════════════════════════════════════════════════════
# XLSX
# ═════════════════════════════════════════════════════════════════════════════

def _extract_xlsx(path: Path) -> ExtractedDocument:
    doc = ExtractedDocument(path=str(path), kind="xlsx")
    try:
        from openpyxl import load_workbook
        data = _safe_read_bytes(path)
        doc.bytes_read = len(data)
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        doc.metadata = {
            "sheet_names": wb.sheetnames,
            "sheets": len(wb.sheetnames),
        }
        text_lines: list[str] = []
        all_tables: list[list[list[str]]] = []
        for ws in wb.worksheets:
            text_lines.append(f"## Sheet: {ws.title}")
            sheet_rows: list[list[str]] = []
            for row in ws.iter_rows(values_only=True):
                if all(c is None or c == "" for c in row):
                    continue
                sheet_rows.append([str(c) if c is not None else "" for c in row])
                text_lines.append("\t".join(sheet_rows[-1]))
            if sheet_rows:
                all_tables.append(sheet_rows)
        doc.text = "\n".join(text_lines)
        # Cap embedded tables (can be huge)
        doc.tables = all_tables[:20]
    except ImportError:
        doc.error = "Install openpyxl for XLSX extraction"
    except Exception as e:
        doc.error = f"XLSX extraction failed: {e}"
    return doc


# ═════════════════════════════════════════════════════════════════════════════
# PPTX
# ═════════════════════════════════════════════════════════════════════════════

def _extract_pptx(path: Path) -> ExtractedDocument:
    doc = ExtractedDocument(path=str(path), kind="pptx")
    try:
        from pptx import Presentation
        data = _safe_read_bytes(path)
        doc.bytes_read = len(data)
        prs = Presentation(io.BytesIO(data))
        doc.pages = len(prs.slides)
        lines: list[str] = []
        for i, slide in enumerate(prs.slides, 1):
            lines.append(f"\n--- Slide {i} ---")
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for p in shape.text_frame.paragraphs:
                        txt = "".join(r.text for r in p.runs)
                        if txt.strip():
                            lines.append(txt)
        doc.text = "\n".join(lines)
        doc.metadata = {"slides": doc.pages}
    except ImportError:
        doc.error = "Install python-pptx for PPTX extraction"
    except Exception as e:
        doc.error = f"PPTX extraction failed: {e}"
    return doc


# ═════════════════════════════════════════════════════════════════════════════
# CSV
# ═════════════════════════════════════════════════════════════════════════════

def _extract_csv(path: Path) -> ExtractedDocument:
    doc = ExtractedDocument(path=str(path), kind="csv")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore", newline="") as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.reader(f, dialect)
            rows: list[list[str]] = []
            for i, row in enumerate(reader):
                if i > 5000:
                    break
                rows.append([(c or "").strip() for c in row])
        if rows:
            header = rows[0]
            doc.metadata = {
                "rows": len(rows) - 1,
                "columns": len(header),
                "column_names": header,
                "delimiter": dialect.delimiter,
            }
        doc.tables = [rows]
        doc.text = "\n".join(",".join(r) for r in rows[:200])
    except Exception as e:
        doc.error = f"CSV extraction failed: {e}"
    return doc


# ═════════════════════════════════════════════════════════════════════════════
# JSON
# ═════════════════════════════════════════════════════════════════════════════

def _extract_json(path: Path) -> ExtractedDocument:
    doc = ExtractedDocument(path=str(path), kind="json")
    try:
        data = json.loads(_safe_read_bytes(path).decode("utf-8", errors="ignore"))
        doc.metadata = {
            "type": type(data).__name__,
            "size": len(doc.text),
        }
        if isinstance(data, dict):
            doc.metadata["keys"] = list(data.keys())[:30]
            doc.text = json.dumps(data, indent=2, ensure_ascii=False)[:200_000]
        elif isinstance(data, list):
            doc.metadata["length"] = len(data)
            doc.text = json.dumps(data[:200], indent=2, ensure_ascii=False)
        else:
            doc.text = json.dumps(data, indent=2, ensure_ascii=False)
    except Exception as e:
        doc.error = f"JSON extraction failed: {e}"
    return doc


# ═════════════════════════════════════════════════════════════════════════════
# XML / HTML
# ═════════════════════════════════════════════════════════════════════════════

_HTML_STRIP_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _extract_xml(path: Path) -> ExtractedDocument:
    doc = ExtractedDocument(path=str(path), kind="xml")
    try:
        text = _safe_read_bytes(path).decode("utf-8", errors="ignore")
        root = ET.fromstring(text)
        # Walk the tree, gathering tag names
        tags: dict[str, int] = {}
        text_parts: list[str] = []
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            tags[tag] = tags.get(tag, 0) + 1
            if elem.text and elem.text.strip():
                text_parts.append(elem.text.strip())
        doc.metadata = {"tags": tags, "total_elements": sum(tags.values())}
        doc.text = "\n".join(text_parts)
    except Exception as e:
        # Fallback: treat as text
        try:
            doc.text = _safe_read_bytes(path).decode("utf-8", errors="ignore")
            doc.kind = "text"
            doc.warnings.append(str(e))
        except Exception:
            doc.error = f"XML extraction failed: {e}"
    return doc


def _extract_html(path: Path) -> ExtractedDocument:
    doc = ExtractedDocument(path=str(path), kind="html")
    try:
        raw = _safe_read_bytes(path).decode("utf-8", errors="ignore")
        # Title
        title_m = re.search(r"<title[^>]*>(.*?)</title>", raw,
                            re.IGNORECASE | re.DOTALL)
        doc.metadata["title"] = title_m.group(1).strip() if title_m else ""
        # Meta description
        desc_m = re.search(
            r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']',
            raw, re.IGNORECASE,
        )
        if desc_m:
            doc.metadata["description"] = desc_m.group(1).strip()
        # Plain text (strip tags)
        text = _HTML_STRIP_RE.sub(" ", raw)
        text = _WS_RE.sub(" ", text).strip()
        doc.text = text
        doc.warnings.append("HTML parsed with naive regex; consider BeautifulSoup for accuracy")
    except Exception as e:
        doc.error = f"HTML extraction failed: {e}"
    return doc


# ═════════════════════════════════════════════════════════════════════════════
# Plain text / code
# ═════════════════════════════════════════════════════════════════════════════

def _extract_text(path: Path) -> ExtractedDocument:
    doc = ExtractedDocument(path=str(path), kind="text")
    try:
        doc.text = _safe_read_bytes(path).decode("utf-8", errors="ignore")
        doc.bytes_read = len(doc.text.encode("utf-8"))
    except Exception as e:
        doc.error = f"Text extraction failed: {e}"
    return doc


def _extract_python(path: Path) -> ExtractedDocument:
    """Python-specific: extract docstrings, function/class signatures, imports."""
    doc = ExtractedDocument(path=str(path), kind="code")
    try:
        source = _safe_read_bytes(path).decode("utf-8", errors="ignore")
        doc.text = source
        doc.bytes_read = len(source.encode("utf-8"))

        # Imports
        imports: list[str] = []
        try:
            tree = __import__("ast").parse(source)
            for node in tree.body:
                if isinstance(node, __import__("ast").Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, __import__("ast").ImportFrom):
                    imports.append(f"{node.module or ''}.")
        except SyntaxError as e:
            doc.warnings.append(f"Python syntax error: {e}")

        # Tokenize to count lines / get signatures
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
            sig_lines: list[str] = []
            for tok in tokens:
                if tok.type == tokenize.NAME and tok.string in ("def", "class"):
                    sig_lines.append(tok.line.rstrip())
        except Exception:
            sig_lines = []

        doc.metadata = {
            "imports": imports,
            "definitions": sig_lines[:50],
            "lines": source.count("\n") + 1,
            "bytes": len(source),
        }
    except Exception as e:
        doc.error = f"Python extraction failed: {e}"
    return doc


# ═════════════════════════════════════════════════════════════════════════════
# Image OCR (optional — tesseract / easyocr)
# ═════════════════════════════════════════════════════════════════════════════

def _extract_image(path: Path) -> ExtractedDocument:
    doc = ExtractedDocument(path=str(path), kind="image")
    try:
        from PIL import Image
        img = Image.open(path)
        doc.metadata = {
            "format": img.format,
            "size": img.size,
            "mode": img.mode,
        }
        doc.bytes_read = Path(path).stat().st_size
        # Try pytesseract first
        try:
            import pytesseract  # type: ignore
            doc.text = pytesseract.image_to_string(img)
        except ImportError:
            doc.warnings.append(
                "Install pytesseract + tesseract-ocr for OCR text extraction"
            )
    except ImportError:
        doc.error = "Install Pillow for image metadata"
    except Exception as e:
        doc.error = f"Image extraction failed: {e}"
    return doc


# ═════════════════════════════════════════════════════════════════════════════
# Dispatcher
# ═════════════════════════════════════════════════════════════════════════════

_EXT_MAP = {
    ".pdf":  _extract_pdf,
    ".docx": _extract_docx,
    ".doc":  _extract_docx,        # best-effort
    ".xlsx": _extract_xlsx,
    ".xls":  _extract_xlsx,
    ".xlsm": _extract_xlsx,
    ".pptx": _extract_pptx,
    ".ppt":  _extract_pptx,
    ".csv":  _extract_csv,
    ".tsv":  _extract_csv,
    ".json": _extract_json,
    ".xml":  _extract_xml,
    ".html": _extract_html,
    ".htm":  _extract_html,
    ".py":   _extract_python,
    ".txt":  _extract_text,
    ".md":   _extract_text,
    ".markdown": _extract_text,
    ".log":  _extract_text,
    ".ini":  _extract_text,
    ".cfg":  _extract_text,
    ".yaml": _extract_text,
    ".yml":  _extract_text,
    ".toml": _extract_text,
    # Image extensions → OCR
    ".png":  _extract_image,
    ".jpg":  _extract_image,
    ".jpeg": _extract_image,
    ".bmp":  _extract_image,
    ".gif":  _extract_image,
    ".tiff": _extract_image,
    ".webp": _extract_image,
}


class ContentExtractor:
    """Dispatch content extraction by file extension."""

    def extract(self, path: str | Path) -> ExtractedDocument:
        p = Path(path)
        if not p.exists():
            return ExtractedDocument(path=str(p), kind="", error=f"Not found: {p}")
        ext = p.suffix.lower()
        fn = _EXT_MAP.get(ext)
        if fn is None:
            # Try MIME type detection
            mime, _ = mimetypes.guess_type(str(p))
            if mime == "application/pdf":
                fn = _extract_pdf
            elif mime == "text/plain":
                fn = _extract_text
            elif mime and mime.startswith("text/"):
                fn = _extract_text
        if fn is None:
            return ExtractedDocument(
                path=str(p), kind="",
                error=f"Unsupported extension: {ext!r}",
                warnings=[f"Supported: {sorted(_EXT_MAP.keys())}"],
            )
        return fn(p)

    def supported_extensions(self) -> list[str]:
        return sorted(_EXT_MAP.keys())


# ═════════════════════════════════════════════════════════════════════════════
# Singleton
# ═════════════════════════════════════════════════════════════════════════════

_INSTANCE: Optional[ContentExtractor] = None


def extractor() -> ContentExtractor:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ContentExtractor()
    return _INSTANCE


def extract(path: str | Path) -> ExtractedDocument:
    """One-liner: ``extract('/path/to/file.pdf')``."""
    return extractor().extract(path)


__all__ = [
    "ContentExtractor", "ExtractedDocument",
    "extractor", "extract",
]
