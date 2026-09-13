from __future__ import annotations

import json
import re
from .models import CodingResult


class OutputParser:
    FILE_PATTERNS = [
        re.compile(r"(?:modified|created|updated|changed|wrote|edited|written|saved|generated)\s+(.+)", re.I),
        re.compile(r"(?:file[s]?\s+changed[:\s])+(.+)", re.I),
        re.compile(r"(?:writing|creating|editing)\s+(.+)", re.I),
        re.compile(r"(?:→|->)\s*(.+)", re.I),
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

        # Try JSON parsing first (OpenCode may output structured events)
        try:
            json_result = cls._try_parse_json(raw)
            if json_result:
                return json_result
        except Exception:
            pass

        # Fall back to regex text parsing
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            for pat in cls.FILE_PATTERNS:
                m = pat.search(stripped)
                if m:
                    fname = m.group(1).strip().rstrip(".,;")
                    if fname and len(fname) < 200:
                        files.append(fname)
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

    @classmethod
    def _try_parse_json(cls, raw: str) -> CodingResult | None:
        """Try to parse OpenCode JSON event output."""
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        if not lines:
            return None

        files = []
        errors = []
        summary_parts = []

        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")

            if event_type == "file_write" or event_type == "file_edit":
                path = event.get("path", "") or event.get("file", "")
                if path:
                    files.append(path)

            elif event_type == "error":
                msg = event.get("message", "") or event.get("error", "")
                if msg:
                    errors.append(msg[:200])

            elif event_type == "message":
                text = event.get("text", "") or event.get("content", "")
                if text:
                    summary_parts.append(text[:300])

        if not files and not errors and not summary_parts:
            return None

        summary = summary_parts[-1] if summary_parts else _extract_summary(raw)

        return CodingResult(
            success=len(errors) == 0,
            status="SUCCEEDED" if len(errors) == 0 else "FAILED",
            summary=summary,
            files_changed=files,
            errors=errors,
            warnings=[],
            raw_output=raw[:5000],
        )


def _extract_summary(raw: str) -> str:
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if not lines:
        return "No output captured."
    # Look for meaningful summary lines
    for line in lines[-15:]:
        low = line.lower()
        if any(kw in low for kw in ("done", "complete", "success", "fix",
                                     "implement", "change", "modify", "error",
                                     "created", "wrote", "saved", "finished")):
            return line[:300]
    # Return last non-empty line
    for line in reversed(lines):
        if len(line) > 5:
            return line[:300]
    return lines[-1][:300]
