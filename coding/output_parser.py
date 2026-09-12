from __future__ import annotations

import re
from .models import CodingResult


class OutputParser:
    FILE_PATTERNS = [
        re.compile(r"(?:modified|created|updated|changed|wrote|edited)\s+(.+)", re.I),
        re.compile(r"(?:file[s]?\s+changed[:\s])+(.+)", re.I),
    ]
    ERROR_PATTERNS = [
        re.compile(r"(?:error|exception|traceback|failed|fatal)[:\s]*(.+)", re.I),
    ]
    WARN_PATTERNS = [
        re.compile(r"(?:warning|warn)[:\s]*(.+)", re.I),
    ]

    @classmethod
    def parse(cls, raw: str, success: bool) -> CodingResult:
        files: list[str] = []
        errors: list[str] = []
        warnings: list[str] = []

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            for pat in cls.FILE_PATTERNS:
                m = pat.search(stripped)
                if m:
                    files.append(m.group(1).strip().rstrip(".,;"))
            for pat in cls.ERROR_PATTERNS:
                m = pat.search(stripped)
                if m:
                    errors.append(m.group(0).strip()[:200])
            for pat in cls.WARN_PATTERNS:
                m = pat.search(stripped)
                if m:
                    warnings.append(m.group(0).strip()[:200])

        summary = _extract_summary(raw)

        return CodingResult(
            success=success,
            status="SUCCEEDED" if success else "FAILED",
            summary=summary,
            files_changed=files,
            errors=errors,
            warnings=warnings,
            raw_output=raw[:5000],
        )


def _extract_summary(raw: str) -> str:
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if not lines:
        return "No output captured."
    for line in lines[-10:]:
        low = line.lower()
        if any(kw in low for kw in ("done", "complete", "success", "fix",
                                     "implement", "change", "modify", "error")):
            return line[:300]
    return lines[-1][:300]
