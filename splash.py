"""SONIC AI — Video Intro (VLC-based).

Plays intro video on startup using VLC.
Renders directly into the widget — same window, no separate window.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from threading import Thread

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QPushButton, QWidget

import vlc


class SonicIntro(QWidget):
    def __init__(self, video_path: str, on_done=None) -> None:
        super().__init__()
        self._on_done = on_done
        self._video_path = video_path
        self._done = False
        self._player = None
        self._instance = None

        self.setStyleSheet("background: black;")
        self.setAutoFillBackground(True)

        # ── Skip button ──────────────────────────────────────────────────
        self._skip_btn = QPushButton("SKIP  >>", self)
        self._skip_btn.setFixedSize(100, 36)
        self._skip_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 0, 0, 180);
                color: white;
                border: 1px solid rgba(0, 255, 255, 80);
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: rgba(0, 212, 255, 60);
                border: 1px solid rgba(0, 212, 255, 200);
            }
        """)
        self._skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skip_btn.clicked.connect(self._skip)
        self._skip_btn.raise_()

        # Start video after widget is shown and has size
        QTimer.singleShot(300, self._start_video)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._skip_btn.move(20, 20)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Ensure widget has proper size before starting video
        self.setMinimumSize(400, 300)

    def _start_video(self) -> None:
        if not self._video_path or not os.path.exists(self._video_path):
            print(f"[INTRO] Video not found: {self._video_path}")
            self._finish()
            return

        try:
            # Create VLC instance
            self._instance = vlc.Instance("--no-xlib", "--quiet")
            self._player = self._instance.media_player_new()

            # Set window handle for rendering INTO this widget
            self._player.set_hwnd(int(self.winId()))

            # Load and play
            media = self._instance.media_new(self._video_path)
            self._player.set_media(media)
            self._player.audio_set_volume(100)
            self._player.play()

            print("[INTRO] Video playing via VLC...")

            # Monitor video end in background thread
            Thread(target=self._monitor_end, daemon=True).start()

        except Exception as e:
            print(f"[INTRO] VLC error: {e}")
            self._finish()

    def _monitor_end(self) -> None:
        """Wait for video to finish playing."""
        time.sleep(1)  # Give VLC time to start
        while True:
            state = self._player.get_state()
            if state in (vlc.State.Ended, vlc.State.Stopped, vlc.State.Error):
                break
            time.sleep(0.2)

        if not self._done:
            print("[INTRO] Video ended")
            QTimer.singleShot(0, self._finish)

    def _skip(self) -> None:
        if self._player:
            self._player.stop()
        self._finish()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        if self._player:
            try:
                self._player.stop()
            except Exception:
                pass
        print("[INTRO] Done")
        if self._on_done:
            self._on_done()
