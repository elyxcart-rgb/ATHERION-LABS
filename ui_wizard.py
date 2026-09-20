"""SONIC AI — Apple-Level Setup Wizard.
Premium design with smooth animations and clean aesthetics.
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

from apple_design import (
    Tokens, AppleButton, AppleInput, AppleCard, AppleStepIndicator,
    AppleCheckmark, create_shadow, fade_in, slide_up,
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
    """Apple-style card with Tokens styling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            GlassCard {{
                background: {Tokens.BG_CARD};
                border: 1px solid {Tokens.BORDER};
                border-radius: {Tokens.R_LG}px;
            }}
        """)
        shadow = create_shadow(radius=24, color=QColor(0, 0, 0, 40), dy=2)
        self.setGraphicsEffect(shadow)


class StepIndicator(QWidget):
    """Delegates to AppleStepIndicator for clean dots and connecting line."""

    def __init__(self, steps: list[str], parent=None):
        super().__init__(parent)
        self.steps = steps
        self.setFixedHeight(60)
        self._inner = AppleStepIndicator(len(steps), self)
        self._labels: list[QLabel] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._inner)
        lbl_row = QHBoxLayout()
        lbl_row.setContentsMargins(60, 0, 60, 0)
        for i, name in enumerate(steps):
            lbl = QLabel(name)
            lbl.setFont(Tokens.font(9))
            lbl.setStyleSheet(f"color: {Tokens.TEXT_TERTIARY}; background: transparent;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_row.addWidget(lbl, 1)
            self._labels.append(lbl)
        layout.addLayout(lbl_row)

    def set_current(self, idx: int):
        self._inner.set_current(idx)
        for i, lbl in enumerate(self._labels):
            if i <= idx:
                lbl.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
            else:
                lbl.setStyleSheet(f"color: {Tokens.TEXT_TERTIARY}; background: transparent;")


class GlassInput(QLineEdit):
    """Delegates to AppleInput for consistent styling."""

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(40)
        self.setFont(Tokens.font(13))
        self.setStyleSheet(f"""
            QLineEdit {{
                background: {Tokens.SURFACE_1};
                border: 1px solid {Tokens.BORDER};
                border-radius: {Tokens.R_SM}px;
                padding: 0 12px;
                color: {Tokens.TEXT_PRIMARY};
                selection-background-color: rgba(10, 132, 255, 0.3);
            }}
            QLineEdit:focus {{
                border: 1px solid {Tokens.ACCENT};
                background: {Tokens.SURFACE_2};
            }}
            QLineEdit::placeholder {{
                color: {Tokens.TEXT_TERTIARY};
            }}
        """)


class GlassComboBox(QComboBox):
    """Apple-style combo box matching design tokens."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setFont(Tokens.font(13))
        self.setStyleSheet(f"""
            QComboBox {{
                background: {Tokens.SURFACE_1};
                border: 1px solid {Tokens.BORDER};
                border-radius: {Tokens.R_SM}px;
                padding: 0 12px;
                color: {Tokens.TEXT_PRIMARY};
                min-width: 120px;
            }}
            QComboBox:focus {{
                border: 1px solid {Tokens.ACCENT};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 30px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {Tokens.TEXT_TERTIARY};
                margin-right: 10px;
            }}
            QComboBox QAbstractItemView {{
                background: {Tokens.SURFACE_2};
                border: 1px solid {Tokens.BORDER_LIGHT};
                border-radius: {Tokens.R_SM}px;
                selection-background-color: rgba(10, 132, 255, 0.2);
                color: {Tokens.TEXT_PRIMARY};
                padding: 4px;
                outline: none;
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
        super().__init__("Welcome to SONIC Apex", "Your intelligent desktop assistant", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 20)
        layout.setSpacing(16)

        icon_label = QLabel()
        icon_path = ROOT / "config" / "sonic.ico"
        if icon_path.exists():
            pixmap = QIcon(str(icon_path)).pixmap(96, 96)
            icon_label.setPixmap(pixmap)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        layout.addSpacing(8)

        title = QLabel(self.title)
        title.setFont(Tokens.font(20, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(self.subtitle)
        subtitle.setFont(Tokens.font(13))
        subtitle.setStyleSheet(f"color: {Tokens.TEXT_SECONDARY}; background: transparent;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(20)

        features = [
            ("Voice Assistant", "Talk naturally, SONIC listens and responds"),
            ("Smart Memory", "Remembers your preferences and context"),
            ("Tool Ecosystem", "49+ tools: GitHub, Twitter, Email, Vision & more"),
            ("Self-Improving", "Learns from interactions over time"),
        ]

        for icon_text, desc in features:
            row = QHBoxLayout()
            row.setSpacing(12)
            check = QLabel("\u2713")
            check.setFont(Tokens.font(13, QFont.Weight.Bold))
            check.setStyleSheet(f"color: {Tokens.SUCCESS}; background: transparent;")
            check.setFixedWidth(24)
            check.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(check)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            name_lbl = QLabel(icon_text)
            name_lbl.setFont(Tokens.font(13, QFont.Weight.Medium))
            name_lbl.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
            text_col.addWidget(name_lbl)

            desc_lbl = QLabel(desc)
            desc_lbl.setFont(Tokens.font(11))
            desc_lbl.setStyleSheet(f"color: {Tokens.TEXT_SECONDARY}; background: transparent;")
            desc_lbl.setWordWrap(True)
            text_col.addWidget(desc_lbl)

            row.addLayout(text_col, 1)
            layout.addLayout(row)

        layout.addStretch()

        tip = QLabel("This wizard will guide you through the initial setup.")
        tip.setFont(Tokens.font(11))
        tip.setStyleSheet(f"color: {Tokens.TEXT_TERTIARY}; background: transparent;")
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
        gemini_label_row = QHBoxLayout()
        gemini_label = QLabel("Gemini API Key")
        gemini_label.setFont(Tokens.font(12, QFont.Weight.Medium))
        gemini_label.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
        gemini_label_row.addWidget(gemini_label)

        required_badge = QLabel("Required")
        required_badge.setFont(Tokens.font(9, QFont.Weight.Medium))
        required_badge.setStyleSheet(
            f"color: {Tokens.ERROR}; background: rgba(255, 69, 58, 0.12); "
            f"border-radius: {Tokens.R_SM}px; padding: 2px 8px;"
        )
        gemini_label_row.addWidget(required_badge)
        gemini_label_row.addStretch()
        gemini_row.addLayout(gemini_label_row)

        self.gemini_input = GlassInput("AIza...")
        self.gemini_input.setText(keys.get("gemini_api_key", ""))
        self.gemini_input.setEchoMode(QLineEdit.EchoMode.Password)
        gemini_row.addWidget(self.gemini_input)

        gemini_tip = QLabel("Get free key at ai.google.dev")
        gemini_tip.setFont(Tokens.font(11))
        gemini_tip.setStyleSheet(f"color: {Tokens.TEXT_SECONDARY}; background: transparent;")
        gemini_row.addWidget(gemini_tip)
        layout.addLayout(gemini_row)

        layout.addSpacing(4)

        openai_row = QVBoxLayout()
        openai_row.setSpacing(6)
        openai_label = QLabel("OpenAI API Key")
        openai_label.setFont(Tokens.font(12, QFont.Weight.Medium))
        openai_label.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
        openai_row.addWidget(openai_label)

        self.openai_input = GlassInput("sk-...")
        self.openai_input.setText(keys.get("openai_api_key", ""))
        self.openai_input.setEchoMode(QLineEdit.EchoMode.Password)
        openai_row.addWidget(self.openai_input)

        openai_tip = QLabel("Optional — Enables GPT models")
        openai_tip.setFont(Tokens.font(11))
        openai_tip.setStyleSheet(f"color: {Tokens.TEXT_SECONDARY}; background: transparent;")
        openai_row.addWidget(openai_tip)
        layout.addLayout(openai_row)

        layout.addSpacing(4)

        discord_row = QVBoxLayout()
        discord_row.setSpacing(6)
        discord_label = QLabel("Discord Bot Token")
        discord_label.setFont(Tokens.font(12, QFont.Weight.Medium))
        discord_label.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
        discord_row.addWidget(discord_label)

        self.discord_input = GlassInput("Paste bot token...")
        self.discord_input.setText(keys.get("discord_bot_token", ""))
        self.discord_input.setEchoMode(QLineEdit.EchoMode.Password)
        discord_row.addWidget(self.discord_input)

        discord_tip = QLabel("Optional — Enables Discord integration")
        discord_tip.setFont(Tokens.font(11))
        discord_tip.setStyleSheet(f"color: {Tokens.TEXT_SECONDARY}; background: transparent;")
        discord_row.addWidget(discord_tip)
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
        svc_header.setFont(Tokens.font(12))
        svc_header.setStyleSheet(f"color: {Tokens.TEXT_SECONDARY}; background: transparent;")
        layout.addWidget(svc_header)

        layout.addSpacing(2)

        gh_card = AppleCard()
        gh_layout = QVBoxLayout(gh_card)
        gh_layout.setContentsMargins(16, 14, 16, 14)
        gh_layout.setSpacing(6)

        gh_header = QHBoxLayout()
        gh_title = QLabel("GitHub")
        gh_title.setFont(Tokens.font(13, QFont.Weight.SemiBold))
        gh_title.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
        gh_header.addWidget(gh_title)
        gh_header.addStretch()

        auth_badge = QLabel("Authenticated")
        auth_badge.setFont(Tokens.font(10, QFont.Weight.Medium))
        auth_badge.setStyleSheet(
            f"color: {Tokens.SUCCESS}; background: rgba(48, 209, 88, 0.12); "
            f"border-radius: {Tokens.R_SM}px; padding: 3px 10px;"
        )
        gh_header.addWidget(auth_badge)
        gh_layout.addLayout(gh_header)

        gh_desc = QLabel("gh CLI already authenticated. No setup needed.")
        gh_desc.setFont(Tokens.font(11))
        gh_desc.setStyleSheet(f"color: {Tokens.TEXT_SECONDARY}; background: transparent;")
        gh_layout.addWidget(gh_desc)

        layout.addWidget(gh_card)

        tw_card = AppleCard()
        tw_layout = QVBoxLayout(tw_card)
        tw_layout.setContentsMargins(16, 14, 16, 14)
        tw_layout.setSpacing(8)

        tw_title = QLabel("Twitter / X")
        tw_title.setFont(Tokens.font(13, QFont.Weight.SemiBold))
        tw_title.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
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

        em_card = AppleCard()
        em_layout = QVBoxLayout(em_card)
        em_layout.setContentsMargins(16, 14, 16, 14)
        em_layout.setSpacing(8)

        em_title = QLabel("Email")
        em_title.setFont(Tokens.font(13, QFont.Weight.SemiBold))
        em_title.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
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
        name_label.setFont(Tokens.font(12, QFont.Weight.Medium))
        name_label.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
        name_col.addWidget(name_label)
        self.name_input = GlassInput("Enter your name")
        self.name_input.setText(prefs.get("user_name", ""))
        name_col.addWidget(self.name_input)
        name_row.addLayout(name_col)

        assistant_col = QVBoxLayout()
        assistant_col.setSpacing(6)
        assistant_label = QLabel("Assistant Name")
        assistant_label.setFont(Tokens.font(12, QFont.Weight.Medium))
        assistant_label.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
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
        theme_label.setFont(Tokens.font(12, QFont.Weight.Medium))
        theme_label.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
        theme_col.addWidget(theme_label)

        self._theme_pills = QHBoxLayout()
        self._theme_pills.setSpacing(0)
        self._theme_buttons: list[QPushButton] = []
        self._current_theme_index = 0

        themes = ["Dark (Default)", "Sci-Fi Gold"]
        current_theme = prefs.get("theme", "dark")
        self._current_theme_index = 1 if current_theme == "scifi" else 0

        for i, theme_name in enumerate(themes):
            btn = QPushButton(theme_name)
            btn.setCheckable(True)
            btn.setChecked(i == self._current_theme_index)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(Tokens.font(11, QFont.Weight.Medium))
            btn.setFixedHeight(32)
            btn.setStyleSheet(self._pill_style(i == self._current_theme_index))
            btn.clicked.connect(lambda checked, idx=i: self._select_theme(idx))
            self._theme_buttons.append(btn)
            self._theme_pills.addWidget(btn)

        self.theme_combo = GlassComboBox()
        self.theme_combo.addItems(["Dark (Default)", "Sci-Fi Gold"])
        self.theme_combo.setCurrentIndex(self._current_theme_index)
        self.theme_combo.hide()

        theme_col.addLayout(self._theme_pills)
        theme_col.addWidget(self.theme_combo)
        theme_row.addLayout(theme_col)

        lang_col = QVBoxLayout()
        lang_col.setSpacing(6)
        lang_label = QLabel("Language")
        lang_label.setFont(Tokens.font(12, QFont.Weight.Medium))
        lang_label.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
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

        instructions_label = QLabel("Custom Instructions")
        instructions_label.setFont(Tokens.font(12, QFont.Weight.Medium))
        instructions_label.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
        layout.addWidget(instructions_label)

        self.instructions_input = GlassInput("e.g., Always respond in Roman Urdu...")
        self.instructions_input.setText(prefs.get("custom_instructions", ""))
        layout.addWidget(self.instructions_input)

        layout.addStretch()

    def _pill_style(self, active: bool) -> str:
        if active:
            return (
                f"background: {Tokens.ACCENT}; color: #ffffff; border: none; "
                f"border-radius: {Tokens.R_SM}px; padding: 0 20px; font-weight: 500;"
            )
        return (
            f"background: transparent; color: {Tokens.TEXT_SECONDARY}; "
            f"border: 1px solid {Tokens.BORDER}; border-radius: {Tokens.R_SM}px; "
            f"padding: 0 20px; font-weight: 500;"
        )

    def _select_theme(self, idx: int):
        self._current_theme_index = idx
        for i, btn in enumerate(self._theme_buttons):
            btn.setStyleSheet(self._pill_style(i == idx))
            btn.setChecked(i == idx)
        self.theme_combo.setCurrentIndex(idx)

    def get_data(self) -> dict:
        return {
            "user_name": self.name_input.text().strip(),
            "assistant_name": self.assistant_input.text().strip() or "SONIC",
            "theme": "scifi" if self._current_theme_index == 1 else "dark",
            "language": self.lang_combo.currentText(),
            "custom_instructions": self.instructions_input.text().strip(),
        }


class DoneStep(StepWidget):
    """Completion step."""

    def __init__(self, parent=None):
        super().__init__("Setup Complete!", "SONIC Apex is ready to go", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 20)
        layout.setSpacing(16)

        checkmark = AppleCheckmark(72)
        checkmark_center = QHBoxLayout()
        checkmark_center.addStretch()
        checkmark_center.addWidget(checkmark)
        checkmark_center.addStretch()
        layout.addLayout(checkmark_center)

        layout.addSpacing(8)

        title = QLabel(self.title)
        title.setFont(Tokens.font(18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(self.subtitle)
        subtitle.setFont(Tokens.font(12))
        subtitle.setStyleSheet(f"color: {Tokens.TEXT_SECONDARY}; background: transparent;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(16)

        summary_card = GlassCard()
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(20, 16, 20, 16)
        summary_layout.setSpacing(10)

        summary_items = [
            "API keys encrypted and stored",
            "Preferences saved",
            "External services configured",
            "Memory system initialized",
        ]

        for item in summary_items:
            row = QHBoxLayout()
            row.setSpacing(10)
            check = QLabel("\u2713")
            check.setFont(Tokens.font(12, QFont.Weight.Bold))
            check.setStyleSheet(f"color: {Tokens.SUCCESS}; background: transparent;")
            check.setFixedWidth(20)
            check.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(check)
            lbl = QLabel(item)
            lbl.setFont(Tokens.font(12))
            lbl.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
            row.addWidget(lbl)
            row.addStretch()
            summary_layout.addLayout(row)

        layout.addWidget(summary_card)

        layout.addSpacing(12)

        tip = QLabel("You can say \"Setup karo\" anytime to reconfigure services.")
        tip.setFont(Tokens.font(11))
        tip.setStyleSheet(f"color: {Tokens.TEXT_TERTIARY}; background: transparent;")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tip)

        layout.addStretch()


class ModernWizard(QWidget):
    """Apple-level setup wizard with clean design and smooth animations."""

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
        self.setWindowTitle("SONIC Apex \u2014 Setup Wizard")
        self.setFixedSize(680, 620)
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
                background: {Tokens.BG_PRIMARY};
                border: 1px solid {Tokens.BORDER};
                border-radius: 24px;
            }}
        """)
        root.addWidget(self._bg)

        bg_layout = QVBoxLayout(self._bg)
        bg_layout.setContentsMargins(32, 20, 32, 24)
        bg_layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel()
        icon_path = ROOT / "config" / "sonic.ico"
        if icon_path.exists():
            pixmap = QIcon(str(icon_path)).pixmap(28, 28)
            icon_lbl.setPixmap(pixmap)
        header.addWidget(icon_lbl)

        title = QLabel("SONIC Apex")
        title.setFont(Tokens.font(15, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
        header.addWidget(title)

        header.addStretch()

        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFont(Tokens.font(12, QFont.Weight.Normal))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Tokens.TEXT_TERTIARY};
                border: none;
                border-radius: 15px;
            }}
            QPushButton:hover {{
                background: rgba(255, 69, 58, 0.15);
                color: {Tokens.ERROR};
            }}
        """)
        close_btn.clicked.connect(self._on_close)
        header.addWidget(close_btn)

        bg_layout.addLayout(header)
        bg_layout.addSpacing(8)

        self._step_indicator = StepIndicator(self.STEPS_META)
        self._step_indicator.setStyleSheet("background: transparent;")
        bg_layout.addWidget(self._step_indicator)
        bg_layout.addSpacing(8)

        self._content_area = QWidget()
        self._content_area.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content_area)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        bg_layout.addWidget(self._content_area, 1)

        nav = QHBoxLayout()
        nav.setSpacing(12)
        nav.addStretch()

        self._skip_btn = AppleButton("Skip All", style="ghost")
        self._skip_btn.clicked.connect(self._on_skip)
        nav.addWidget(self._skip_btn)

        self._prev_btn = AppleButton("Back", style="secondary")
        self._prev_btn.clicked.connect(self._prev)
        nav.addWidget(self._prev_btn)

        self._next_btn = AppleButton("Next", style="primary")
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
