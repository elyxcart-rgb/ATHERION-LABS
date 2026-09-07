from PyQt5.QtWidgets import QWidget, QPushButton, QVBoxLayout
from PyQt5.QtCore import Qt
import vlc
import os
import sys
import time
from threading import Thread

class IntroScreen(QWidget):
    def __init__(self, main_window_class):
        super().__init__()
        self.main_window_class = main_window_class
        self.main_window = None
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        video_file = None
        for f in os.listdir(script_dir):
            if "sonic2_processed" in f.lower():
                video_file = os.path.join(script_dir, f)
                break
        
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.showFullScreen()
        self.setStyleSheet("background-color: black;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.skip_btn = QPushButton("SKIP  >>", self)
        self.skip_btn.setFixedSize(100, 40)
        self.skip_btn.move(20, 20)
        self.skip_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 150);
                color: white;
                border: 2px solid white;
                border-radius: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 50);
            }
        """)
        self.skip_btn.setCursor(Qt.PointingHandCursor)
        self.skip_btn.clicked.connect(self.skip_intro)
        self.skip_btn.raise_()
        
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        
        if video_file:
            media = self.instance.media_new(video_file)
            self.player.set_media(media)
        
        self.player.set_fullscreen(False)
        self.player.set_hwnd(int(self.winId()))
        self.player.audio_set_volume(100)
        
        self.player.play()
        
        self.check_thread = Thread(target=self.check_end, daemon=True)
        self.check_thread.start()
    
    def check_end(self):
        time.sleep(1)
        while self.player.get_state() != vlc.State.Ended:
            time.sleep(0.1)
        if self.isVisible():
            self.open_main_window()
    
    def skip_intro(self):
        self.player.stop()
        self.open_main_window()
    
    def open_main_window(self):
        self.main_window = self.main_window_class()
        self.main_window.show()
        self.close()
