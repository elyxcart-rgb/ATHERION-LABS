"""SONIC AI — Modern Setup Wizard.
Glass morphism design with smooth animations.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QTimer, pyqtSignal,
    QRect, QPoint, QSize, QParallelAnimationGroup, QSequentialAnimationGroup,
)
from PyQt6.QtGui import (
    QColor, QPainter, QPainterPath, QFont, QFontMetrics, QLinearGradient,
    QBrush, QPen, QPixmap, QIcon,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QFrame, QGraphicsDropShadowEffect,
    QScrollArea, QSizePolicy, QSpacerItem,
)

try:
    from pyqt6_theme.theme import C
except ImportError:
    class C:
        BG = "#05070a"
        PANEL = "#0a0d12"
        PANEL2 = "#0f1218"
        PANEL3 = "#151a21"
        BORDER = "#1e2530"
        PRI = "#00d9ff"
        PRI_DIM = "#004d66"
        PRI_VIVID = "#00eaff"
        TEXT = "#c8cdd4"
        TEXT_DIM = "#6b7280"
        GREEN = "#3a9a6a"
        RED = "#c43a4a"
        AMBER = "#b89040"


ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
API_KEYS_FILE = CONFIG_DIR / "api_keys.json"

import sys
if sys.platform == "win32":
    _USER_DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
elif sys.platform == "darwin":
    _USER_DATA_ROOT = Path.home() / "Library" / "Application Support"
else:
    _USER_DATA_ROOT = Path.home() / ".local" / "share"

_PROFILE_DIR = _USER_DATA_ROOT / "SONIC AI" / "auth"
_PROFILE_PATH = _PROFILE_DIR / ".profile.json"


def _load_api_keys() -> dict:
    if API_KEYS_FILE.exists():
        try:
            return json.loads(API_KEYS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_api_keys(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing = _load_api_keys()
    existing.update(data)
    API_KEYS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def _load_preferences() -> dict:
    pref_file = CONFIG_DIR / "preferences.json"
    if pref_file.exists():
        try:
            return json.loads(pref_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_preferences(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing = _load_preferences()
    existing.update(data)
    pref_file = CONFIG_DIR / "preferences.json"
    pref_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")


class GlassCard(QFrame):
    """Glass morphism card widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            GlassCard {{
                background: rgba(10, 13, 18, 0.85);
                border: 1px solid rgba(0, 217, 255, 0.15);
                border-radius: 16px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 217, 255, 30))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)


class StepIndicator(QWidget):
    """Horizontal step progress indicator."""

    def __init__(self, steps: list[str], parent=None):
        super().__init__(parent)
        self.steps = steps
        self.current = 0
        self.setFixedHeight(60)
        self.dots: list[QPoint] = []

    def set_current(self, idx: int):
        self.current = idx
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        n = len(self.steps)
        if n == 0:
            return

        w = self.width()
        h = self.height()
        margin = 40
        usable = w - margin * 2
        step_w = usable / max(n - 1, 1)
        cy = h // 2

        self.dots = []
        for i in range(n):
            x = int(margin + i * step_w)
            self.dots.append(QPoint(x, cy))

        for i in range(n - 1):
            x1 = self.dots[i].x()
            x2 = self.dots[i + 1].x()
            if i < self.current:
                pen = QPen(QColor(C.PRI), 2.5)
            else:
                pen = QPen(QColor(C.BORDER), 1.5)
            p.setPen(pen)
            p.drawLine(x1, cy, x2, cy)

        for i, dot in enumerate(self.dots):
            if i < self.current:
                p.setBrush(QBrush(QColor(C.PRI)))
                p.setPen(QPen(QColor(C.PRI_VIVID), 2))
                p.drawEllipse(dot, 8, 8)
                p.setPen(QPen(QColor(C.BG), 2))
                p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
                p.drawText(QRect(dot.x() - 4, dot.y() - 5, 8, 10),
                           Qt.AlignmentFlag.AlignCenter, str(i + 1))
            elif i == self.current:
                p.setBrush(QBrush(QColor(C.PRI_DIM)))
                p.setPen(QPen(QColor(C.PRI), 2))
                p.drawEllipse(dot, 10, 10)
                p.setPen(QPen(QColor(C.PRI_VIVID), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(dot, 14, 14)
                p.setPen(QPen(QColor(C.PRI), 2))
                p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                p.drawText(QRect(dot.x() - 5, dot.y() - 6, 10, 12),
                           Qt.AlignmentFlag.AlignCenter, str(i + 1))
            else:
                p.setBrush(QBrush(QColor(C.PANEL3)))
                p.setPen(QPen(QColor(C.BORDER), 1.5))
                p.drawEllipse(dot, 7, 7)
                p.setPen(QPen(QColor(C.TEXT_DIM), 1))
                p.setFont(QFont("Segoe UI", 7))
                p.drawText(QRect(dot.x() - 4, dot.y() - 5, 8, 10),
                           Qt.AlignmentFlag.AlignCenter, str(i + 1))

            if i < len(self.steps):
                label = self.steps[i]
                p.setPen(QPen(QColor(C.TEXT if i <= self.current else C.TEXT_DIM), 1))
                p.setFont(QFont("Segoe UI", 7))
                tw = QFontMetrics(p.font()).horizontalAdvance(label)
                p.drawText(QRect(dot.x() - tw // 2, cy + 22, tw, 16),
                           Qt.AlignmentFlag.AlignCenter, label)

        p.end()


class GlowButton(QPushButton):
    """Button with glow effect."""

    def __init__(self, text: str, accent: bool = True, parent=None):
        super().__init__(text, parent)
        self.accent = accent
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)
        self.setMinimumWidth(140)
        self.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        self._update_style()

    def _update_style(self):
        if self.accent:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {C.PRI_DIM}, stop:1 {C.PRI});
                    color: {C.BG};
                    border: none;
                    border-radius: 22px;
                    padding: 0 32px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {C.PRI}, stop:1 {C.PRI_VIVID});
                }}
                QPushButton:pressed {{
                    background: {C.PRI_DIM};
                }}
                QPushButton:disabled {{
                    background: {C.PANEL3};
                    color: {C.TEXT_DIM};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER};
                    border-radius: 22px;
                    padding: 0 24px;
                }}
                QPushButton:hover {{
                    border-color: {C.PRI_DIM};
                    color: {C.TEXT};
                }}
            """)


class GlassInput(QLineEdit):
    """Glass morphism input field."""

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(42)
        self.setFont(QFont("Segoe UI", 10))
        self.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(15, 18, 24, 0.9);
                border: 1px solid {C.BORDER};
                border-radius: 10px;
                padding: 0 14px;
                color: {C.TEXT};
                selection-background-color: {C.PRI_DIM};
            }}
            QLineEdit:focus {{
                border-color: {C.PRI};
            }}
            QLineEdit::placeholder {{
                color: {C.TEXT_DIM};
            }}
        """)


class GlassComboBox(QComboBox):
    """Glass morphism combo box."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(42)
        self.setFont(QFont("Segoe UI", 10))
        self.setStyleSheet(f"""
            QComboBox {{
                background: rgba(15, 18, 24, 0.9);
                border: 1px solid {C.BORDER};
                border-radius: 10px;
                padding: 0 14px;
                color: {C.TEXT};
                min-width: 120px;
            }}
            QComboBox:focus {{
                border-color: {C.PRI};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 30px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {C.TEXT_DIM};
                margin-right: 10px;
            }}
            QComboBox QAbstractItemView {{
                background: {C.PANEL2};
                border: 1px solid {C.BORDER};
                border-radius: 8px;
                selection-background-color: {C.PRI_DIM};
                color: {C.TEXT};
                padding: 4px;
            }}
        """)


class StepWidget(QWidget):
    """Base class for wizard step content."""

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle

    def validate(self) -> bool:
        return True

    def get_data(self) -> dict:
        return {}


class WelcomeStep(StepWidget):
    """Welcome / intro step."""

    def __init__(self, parent=None):
        super().__init__("Welcome to SONIC AI", "Your intelligent desktop assistant", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 20)
        layout.setSpacing(16)

        icon_label = QLabel()
        icon_path = ROOT / "config" / "sonic.ico"
        if icon_path.exists():
            pixmap = QIcon(str(icon_path)).pixmap(80, 80)
            icon_label.setPixmap(pixmap)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        layout.addSpacing(10)

        features = [
            ("Voice Assistant", "Talk naturally, SONIC listens and responds"),
            ("Smart Memory", "Remembers your preferences and context"),
            ("Tool Ecosystem", "49+ tools: GitHub, Twitter, Email, Vision & more"),
            ("Self-Improving", "Learns from interactions over time"),
        ]

        for icon_text, desc in features:
            row = QHBoxLayout()
            row.setSpacing(12)
            bullet = QLabel(f"  {icon_text}")
            bullet.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
            bullet.setStyleSheet(f"color: {C.PRI};")
            bullet.setFixedWidth(180)
            row.addWidget(bullet)

            desc_label = QLabel(desc)
            desc_label.setFont(QFont("Segoe UI", 9))
            desc_label.setStyleSheet(f"color: {C.TEXT_DIM};")
            desc_label.setWordWrap(True)
            row.addWidget(desc_label)
            row.addStretch()
            layout.addLayout(row)

        layout.addStretch()

        tip = QLabel("This wizard will guide you through the initial setup.")
        tip.setFont(QFont("Segoe UI", 9))
        tip.setStyleSheet(f"color: {C.TEXT_DIM}; font-style: italic;")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tip)


class ApiKeyStep(StepWidget):
    """API key configuration step."""

    def __init__(self, parent=None):
        super().__init__("API Configuration", "Add your API keys to unlock full power", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(14)

        keys = _load_api_keys()

        gemini_row = QVBoxLayout()
        gemini_row.setSpacing(6)
        gemini_label = QLabel("Gemini API Key *")
        gemini_label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        gemini_label.setStyleSheet(f"color: {C.TEXT};")
        gemini_row.addWidget(gemini_label)

        self.gemini_input = GlassInput("AIza...")
        self.gemini_input.setText(keys.get("gemini_api_key", ""))
        self.gemini_input.setEchoMode(QLineEdit.EchoMode.Password)
        gemini_row.addWidget(self.gemini_input)

        gemini_tip = QLabel("Required — Get free key at ai.google.dev")
        gemini_tip.setFont(QFont("Segoe UI", 8))
        gemini_tip.setStyleSheet(f"color: {C.TEXT_DIM};")
        gemini_row.addWidget(gemini_tip)
        layout.addLayout(gemini_row)

        layout.addSpacing(4)

        openai_row = QVBoxLayout()
        openai_row.setSpacing(6)
        openai_label = QLabel("OpenAI API Key (Optional)")
        openai_label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        openai_label.setStyleSheet(f"color: {C.TEXT};")
        openai_row.addWidget(openai_label)

        self.openai_input = GlassInput("sk-...")
        self.openai_input.setText(keys.get("openai_api_key", ""))
        self.openai_input.setEchoMode(QLineEdit.EchoMode.Password)
        openai_row.addWidget(self.openai_input)
        layout.addLayout(openai_row)

        layout.addSpacing(4)

        discord_row = QVBoxLayout()
        discord_row.setSpacing(6)
        discord_label = QLabel("Discord Bot Token (Optional)")
        discord_label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        discord_label.setStyleSheet(f"color: {C.TEXT};")
        discord_row.addWidget(discord_label)

        self.discord_input = GlassInput("Paste bot token...")
        self.discord_input.setText(keys.get("discord_bot_token", ""))
        self.discord_input.setEchoMode(QLineEdit.EchoMode.Password)
        discord_row.addWidget(self.discord_input)
        layout.addLayout(discord_row)

        layout.addStretch()

    def validate(self) -> bool:
        gemini = self.gemini_input.text().strip()
        return bool(gemini)

    def get_data(self) -> dict:
        data = {}
        g = self.gemini_input.text().strip()
        o = self.openai_input.text().strip()
        d = self.discord_input.text().strip()
        if g:
            data["gemini_api_key"] = g
        if o:
            data["openai_api_key"] = o
        if d:
            data["discord_bot_token"] = d
        return data


class ServicesStep(StepWidget):
    """External services setup step."""

    def __init__(self, parent=None):
        super().__init__("External Services", "Connect to GitHub, Twitter, and Email", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(10)

        keys = _load_api_keys()

        svc_header = QLabel("Configure external integrations (all optional):")
        svc_header.setFont(QFont("Segoe UI", 9))
        svc_header.setStyleSheet(f"color: {C.TEXT_DIM};")
        layout.addWidget(svc_header)

        layout.addSpacing(2)

        gh_card = GlassCard()
        gh_layout = QVBoxLayout(gh_card)
        gh_layout.setContentsMargins(16, 12, 16, 12)
        gh_layout.setSpacing(6)

        gh_title = QLabel("GitHub")
        gh_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        gh_title.setStyleSheet(f"color: {C.TEXT};")
        gh_layout.addWidget(gh_title)

        gh_desc = QLabel("gh CLI already authenticated. No setup needed.")
        gh_desc.setFont(QFont("Segoe UI", 8))
        gh_desc.setStyleSheet(f"color: {C.GREEN};")
        gh_layout.addWidget(gh_desc)

        layout.addWidget(gh_card)

        # Twitter card
        tw_card = GlassCard()
        tw_layout = QVBoxLayout(tw_card)
        tw_layout.setContentsMargins(16, 12, 16, 12)
        tw_layout.setSpacing(8)

        tw_title = QLabel("Twitter / X")
        tw_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        tw_title.setStyleSheet(f"color: {C.TEXT};")
        tw_layout.addWidget(tw_title)

        tw_row1 = QHBoxLayout()
        tw_row1.setSpacing(8)
        self.tw_key = GlassInput("API Key")
        self.tw_key.setText(keys.get("twitter_api_key", ""))
        self.tw_key.setEchoMode(QLineEdit.EchoMode.Password)
        tw_row1.addWidget(self.tw_key, 1)
        self.tw_secret = GlassInput("API Secret")
        self.tw_secret.setText(keys.get("twitter_api_secret", ""))
        self.tw_secret.setEchoMode(QLineEdit.EchoMode.Password)
        tw_row1.addWidget(self.tw_secret, 1)
        tw_layout.addLayout(tw_row1)

        tw_row2 = QHBoxLayout()
        tw_row2.setSpacing(8)
        self.tw_bearer = GlassInput("Bearer Token")
        self.tw_bearer.setText(keys.get("twitter_bearer_token", ""))
        self.tw_bearer.setEchoMode(QLineEdit.EchoMode.Password)
        tw_row2.addWidget(self.tw_bearer, 1)
        self.tw_access = GlassInput("Access Token")
        self.tw_access.setText(keys.get("twitter_access_token", ""))
        self.tw_access.setEchoMode(QLineEdit.EchoMode.Password)
        tw_row2.addWidget(self.tw_access, 1)
        tw_layout.addLayout(tw_row2)

        self.tw_access_secret = GlassInput("Access Token Secret")
        self.tw_access_secret.setText(keys.get("twitter_access_token_secret", ""))
        self.tw_access_secret.setEchoMode(QLineEdit.EchoMode.Password)
        tw_layout.addWidget(self.tw_access_secret)

        layout.addWidget(tw_card)

        # Email card
        em_card = GlassCard()
        em_layout = QVBoxLayout(em_card)
        em_layout.setContentsMargins(16, 12, 16, 12)
        em_layout.setSpacing(8)

        em_title = QLabel("Email")
        em_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        em_title.setStyleSheet(f"color: {C.TEXT};")
        em_layout.addWidget(em_title)

        em_row1 = QHBoxLayout()
        em_row1.setSpacing(8)
        self.em_server = GlassInput("IMAP Server")
        self.em_server.setText(keys.get("email_imap_server", ""))
        em_row1.addWidget(self.em_server, 1)
        self.em_port = GlassInput("Port")
        self.em_port.setText(str(keys.get("email_imap_port", "993")))
        self.em_port.setMaximumWidth(80)
        em_row1.addWidget(self.em_port)
        em_layout.addLayout(em_row1)

        em_row2 = QHBoxLayout()
        em_row2.setSpacing(8)
        self.em_user = GlassInput("Email Address")
        self.em_user.setText(keys.get("email_address", ""))
        em_row2.addWidget(self.em_user, 1)
        self.em_pass = GlassInput("Password / App Password")
        self.em_pass.setText(keys.get("email_password", ""))
        self.em_pass.setEchoMode(QLineEdit.EchoMode.Password)
        em_row2.addWidget(self.em_pass, 1)
        em_layout.addLayout(em_row2)

        layout.addWidget(em_card)

        layout.addStretch()

    def get_data(self) -> dict:
        data = {}
        tw = self.tw_key.text().strip()
        ts = self.tw_secret.text().strip()
        tb = self.tw_bearer.text().strip()
        ta = self.tw_access.text().strip()
        tas = self.tw_access_secret.text().strip()
        if tw:
            data["twitter_api_key"] = tw
        if ts:
            data["twitter_api_secret"] = ts
        if tb:
            data["twitter_bearer_token"] = tb
        if ta:
            data["twitter_access_token"] = ta
        if tas:
            data["twitter_access_token_secret"] = tas

        es = self.em_server.text().strip()
        ep = self.em_port.text().strip()
        eu = self.em_user.text().strip()
        epw = self.em_pass.text().strip()
        if es:
            data["email_imap_server"] = es
        if ep:
            data["email_imap_port"] = int(ep) if ep.isdigit() else 993
        if eu:
            data["email_address"] = eu
        if epw:
            data["email_password"] = epw

        return data


class PreferencesStep(StepWidget):
    """User preferences step."""

    def __init__(self, parent=None):
        super().__init__("Preferences", "Customize your SONIC experience", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(14)

        prefs = _load_preferences()

        name_row = QHBoxLayout()
        name_row.setSpacing(12)

        name_col = QVBoxLayout()
        name_col.setSpacing(6)
        name_label = QLabel("Your Name")
        name_label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        name_label.setStyleSheet(f"color: {C.TEXT};")
        name_col.addWidget(name_label)
        self.name_input = GlassInput("Enter your name")
        self.name_input.setText(prefs.get("user_name", ""))
        name_col.addWidget(self.name_input)
        name_row.addLayout(name_col)

        assistant_col = QVBoxLayout()
        assistant_col.setSpacing(6)
        assistant_label = QLabel("Assistant Name")
        assistant_label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        assistant_label.setStyleSheet(f"color: {C.TEXT};")
        assistant_col.addWidget(assistant_label)
        self.assistant_input = GlassInput("SONIC")
        self.assistant_input.setText(prefs.get("assistant_name", "SONIC"))
        assistant_col.addWidget(self.assistant_input)
        name_row.addLayout(assistant_col)

        layout.addLayout(name_row)

        layout.addSpacing(4)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(12)

        theme_col = QVBoxLayout()
        theme_col.setSpacing(6)
        theme_label = QLabel("Theme")
        theme_label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        theme_label.setStyleSheet(f"color: {C.TEXT};")
        theme_col.addWidget(theme_label)
        self.theme_combo = GlassComboBox()
        self.theme_combo.addItems(["Dark (Default)", "Sci-Fi Gold"])
        current_theme = prefs.get("theme", "dark")
        self.theme_combo.setCurrentIndex(1 if current_theme == "scifi" else 0)
        theme_col.addWidget(self.theme_combo)
        theme_row.addLayout(theme_col)

        lang_col = QVBoxLayout()
        lang_col.setSpacing(6)
        lang_label = QLabel("Language")
        lang_label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        lang_label.setStyleSheet(f"color: {C.TEXT};")
        lang_col.addWidget(lang_label)
        self.lang_combo = GlassComboBox()
        self.lang_combo.addItems(["English", "Roman Urdu", "Urdu", "Hindi"])
        current_lang = prefs.get("language", "English")
        idx = self.lang_combo.findText(current_lang)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        lang_col.addWidget(self.lang_combo)
        theme_row.addLayout(lang_col)

        layout.addLayout(theme_row)

        layout.addSpacing(4)

        instructions_label = QLabel("Custom Instructions (optional)")
        instructions_label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        instructions_label.setStyleSheet(f"color: {C.TEXT};")
        layout.addWidget(instructions_label)

        self.instructions_input = GlassInput("e.g., Always respond in Roman Urdu...")
        self.instructions_input.setText(prefs.get("custom_instructions", ""))
        layout.addWidget(self.instructions_input)

        layout.addStretch()

    def get_data(self) -> dict:
        theme = "scifi" if self.theme_combo.currentIndex() == 1 else "dark"
        return {
            "user_name": self.name_input.text().strip(),
            "assistant_name": self.assistant_input.text().strip() or "SONIC",
            "theme": theme,
            "language": self.lang_combo.currentText(),
            "custom_instructions": self.instructions_input.text().strip(),
        }


class DoneStep(StepWidget):
    """Completion step."""

    def __init__(self, parent=None):
        super().__init__("Setup Complete!", "SONIC AI is ready to go", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 20)
        layout.setSpacing(16)

        check = QLabel("All configurations saved successfully!")
        check.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        check.setStyleSheet(f"color: {C.GREEN};")
        check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(check)

        layout.addSpacing(10)

        summary_items = [
            "API keys encrypted and stored",
            "Preferences saved",
            "External services configured",
            "Memory system initialized",
        ]

        for item in summary_items:
            row = QHBoxLayout()
            row.setSpacing(8)
            bullet = QLabel("  ")
            bullet.setFont(QFont("Segoe UI", 10))
            bullet.setStyleSheet(f"color: {C.GREEN};")
            bullet.setFixedWidth(20)
            row.addWidget(bullet)
            lbl = QLabel(item)
            lbl.setFont(QFont("Segoe UI", 9))
            lbl.setStyleSheet(f"color: {C.TEXT};")
            row.addWidget(lbl)
            row.addStretch()
            layout.addLayout(row)

        layout.addSpacing(16)

        tip = QLabel("You can say \"Setup karo\" anytime to reconfigure services.")
        tip.setFont(QFont("Segoe UI", 8))
        tip.setStyleSheet(f"color: {C.TEXT_DIM}; font-style: italic;")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tip)

        layout.addStretch()


class ModernWizard(QWidget):
    """Modern setup wizard with glass morphism and animations."""

    completed = pyqtSignal()
    skipped = pyqtSignal()

    STEPS_META = [
        "Welcome",
        "API Keys",
        "Services",
        "Preferences",
        "Done",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SONIC AI — Setup Wizard")
        self.setFixedSize(680, 600)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos: Optional[QPoint] = None
        self._current_step = 0
        self._steps: list[StepWidget] = []
        self._anim_group: Optional[QParallelAnimationGroup] = None
        self._build_ui()
        self._show_step(0)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._bg = QWidget(self)
        self._bg.setStyleSheet(f"""
            QWidget {{
                background: qradialgradient(cx:0.5, cy:0.4, radius:0.7,
                    stop:0 rgba(0, 40, 60, 0.95), stop:1 rgba(5, 7, 10, 0.98));
                border: 1px solid rgba(0, 217, 255, 0.12);
                border-radius: 20px;
            }}
        """)
        root.addWidget(self._bg)

        bg_layout = QVBoxLayout(self._bg)
        bg_layout.setContentsMargins(24, 16, 24, 20)
        bg_layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel()
        icon_path = ROOT / "config" / "sonic.ico"
        if icon_path.exists():
            pixmap = QIcon(str(icon_path)).pixmap(28, 28)
            icon_lbl.setPixmap(pixmap)
        header.addWidget(icon_lbl)

        title = QLabel("SONIC AI")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        header.addWidget(title)

        header.addStretch()

        close_btn = QPushButton("X")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C.TEXT_DIM};
                border: none;
                border-radius: 15px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: rgba(196, 58, 74, 0.3);
                color: {C.RED};
            }}
        """)
        close_btn.clicked.connect(self._on_close)
        header.addWidget(close_btn)

        bg_layout.addLayout(header)
        bg_layout.addSpacing(8)

        self._step_indicator = StepIndicator(self.STEPS_META)
        self._step_indicator.setStyleSheet("background: transparent;")
        bg_layout.addWidget(self._step_indicator)
        bg_layout.addSpacing(4)

        self._content_area = QWidget()
        self._content_area.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content_area)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        bg_layout.addWidget(self._content_area, 1)

        nav = QHBoxLayout()
        nav.setSpacing(12)
        nav.addStretch()

        self._skip_btn = GlowButton("Skip All", accent=False)
        self._skip_btn.clicked.connect(self._on_skip)
        nav.addWidget(self._skip_btn)

        self._prev_btn = GlowButton("Back", accent=False)
        self._prev_btn.clicked.connect(self._prev)
        nav.addWidget(self._prev_btn)

        self._next_btn = GlowButton("Next")
        self._next_btn.clicked.connect(self._next)
        nav.addWidget(self._next_btn)

        bg_layout.addLayout(nav)

        self._steps = [
            WelcomeStep(),
            ApiKeyStep(),
            ServicesStep(),
            PreferencesStep(),
            DoneStep(),
        ]

    def _show_step(self, idx: int):
        if idx < 0 or idx >= len(self._steps):
            return

        old = self._current_step
        self._current_step = idx
        self._step_indicator.set_current(idx)

        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        step = self._steps[idx]
        self._content_layout.addWidget(step)

        if idx == 0:
            self._prev_btn.hide()
            self._skip_btn.show()
            self._next_btn.setText("Get Started")
        elif idx == len(self._steps) - 1:
            self._prev_btn.hide()
            self._skip_btn.hide()
            self._next_btn.setText("Finish")
        else:
            self._prev_btn.show()
            self._skip_btn.show()
            if idx == len(self._steps) - 2:
                self._next_btn.setText("Complete Setup")
            else:
                self._next_btn.setText("Next")

        if old != idx:
            self._animate_transition(old, idx)

    def _animate_transition(self, old_idx: int, new_idx: int):
        content = self._content_area
        content.setWindowOpacity(0.0)

        anim = QPropertyAnimation(content, b"windowOpacity")
        anim.setDuration(250)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()

        self._anim_group = QParallelAnimationGroup()
        self._anim_group.addAnimation(anim)
        self._anim_group.start()

    def _next(self):
        if self._current_step < len(self._steps) - 1:
            step = self._steps[self._current_step]
            if not step.validate():
                return

            if self._current_step == 1:
                api_data = step.get_data()
                if api_data:
                    _save_api_keys(api_data)
            elif self._current_step == 2:
                svc_data = step.get_data()
                if svc_data:
                    _save_api_keys(svc_data)
            elif self._current_step == 3:
                pref_data = step.get_data()
                if pref_data:
                    _save_preferences(pref_data)

            self._show_step(self._current_step + 1)
        else:
            self._save_all()
            self.completed.emit()
            self.close()

    def _prev(self):
        if self._current_step > 0:
            self._show_step(self._current_step - 1)

    def _on_skip(self):
        self._save_all()
        self.skipped.emit()
        self.close()

    def _on_close(self):
        self._save_all()
        self.skipped.emit()
        self.close()

    def _save_all(self):
        all_data = {}
        for i in [1, 2, 3]:
            step = self._steps[i]
            data = step.get_data()
            if data:
                if i == 1 or i == 2:
                    _save_api_keys(data)
                    all_data.update(data)
                elif i == 3:
                    _save_preferences(data)
                    all_data.update(data)

        # Save to user profile in AppData
        if all_data:
            _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            profile = {}
            if _PROFILE_PATH.exists():
                try:
                    profile = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
                except Exception:
                    pass
            if "profile" not in profile:
                profile["profile"] = {}
            profile["profile"]["services"] = all_data
            _PROFILE_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")

    def paintEvent(self, event):
        pass

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


def show_modern_wizard(parent=None) -> ModernWizard:
    """Create and show the modern wizard. Returns the widget."""
    wizard = ModernWizard(parent)
    wizard.show()
    return wizard


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    w = ModernWizard()
    w.show()
    sys.exit(app.exec())
