from __future__ import annotations

import re

CODING_KEYWORDS = {
    "fix", "bug", "error", "crash", "debug", "patch", "repair", "broken",
    "refactor", "restructure", "reorganize", "clean", "optimize", "improve",
    "implement", "add", "create", "build", "write", "develop", "feature",
    "new", "integrate", "setup", "configure", "migrate", "upgrade",
    "test", "tests", "unittest", "pytest", "coverage", "lint", "typecheck",
    "deploy", "compile", "bundle", "package",
    "module", "function", "class", "method", "api", "endpoint",
    "code", "coding", "programming", "development",
    "file", "files", "script", "project", "repository", "repo",
    "python", "javascript", "typescript", "html", "css", "rust", "go",
    "dependency", "dependencies", "import", "npm", "pip",
    "variable", "loop", "algorithm", "logic",
    "git", "commit", "branch", "merge",
    "database", "sql", "query", "schema", "migration",
    "regex", "parse", "parser", "tokenizer",
    "diagnostic", "investigate", "inspect", "analyze", "examine",
    "undo", "revert", "rollback", "reset",
    "controller", "handler", "router", "service", "model",
    "component", "widget", "view", "layout", "template",
    "backend", "frontend", "server", "client", "middleware",
}

NON_CODING_KEYWORDS = {
    "weather", "temperature", "forecast", "news", "music", "play",
    "volume", "brightness", "timer", "alarm", "reminder",
    "screenshot", "photo", "image", "video", "camera",
    "send message", "whatsapp", "telegram", "email",
    "open app", "launch", "search google",
    "flight", "hotel", "restaurant", "map",
    "recipe", "cook", "food",
}

_NON_CODING_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(NON_CODING_KEYWORDS, key=len, reverse=True)) + r")\b",
    re.I,
)

class IntentDetector:
    @classmethod
    def is_coding_intent(cls, request: str) -> bool:
        low = request.lower().strip()
        if len(low) < 3:
            return False
        if _NON_CODING_RE.search(low):
            return False
        words = set(re.findall(r"\b\w+\b", low))
        hits = words & CODING_KEYWORDS
        if len(hits) >= 2:
            return True
        if len(hits) == 1:
            has_code_signal = any(s in low for s in [
                ".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go",
                ".html", ".css", ".json", ".yaml", ".toml", ".md",
                "import ", "def ", "class ", "function ", "const ",
                "let ", "var ", "return ", "if ", "for ", "while ",
                "try:", "except", "async ", "await ",
            ])
            if has_code_signal:
                return True
            coding_heavy = {"fix", "bug", "error", "crash", "refactor",
                            "implement", "add", "create", "build", "write",
                            "pytest", "unittest", "lint", "compile",
                            "debug", "patch", "deploy", "migrate"}
            if hits & coding_heavy:
                return True
        return False

    @classmethod
    def classify(cls, request: str) -> str:
        low = request.lower()
        if cls.is_coding_intent(request):
            if any(k in low for k in ("fix", "bug", "error", "crash",
                                       "debug", "broken", "repair")):
                return "debugging"
            if any(k in low for k in ("test", "tests", "pytest", "unittest")):
                return "testing"
            if any(k in low for k in ("refactor", "clean", "optimize",
                                       "restructure")):
                return "refactoring"
            return "coding"
        return "general"
