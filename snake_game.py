"""Professional Snake Game using PyQt6."""

import sys
import random
from enum import Enum
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QLabel, QFrame,
)
from PyQt6.QtCore import pyqtSignal


# ── Constants ────────────────────────────────────────────────────────────────

CELL = 24
COLS = 25
ROWS = 25
WIDTH = COLS * CELL
HEIGHT = ROWS * CELL

# Colors
C_BG        = QColor(15, 15, 25)
C_BORDER    = QColor(40, 40, 60)
C_SNAKE_H   = QColor(0, 220, 120)
C_SNAKE_T   = QColor(0, 140, 70)
C_FOOD      = QColor(255, 60, 80)
C_FOOD_GLOW = QColor(255, 60, 80, 60)
C_GRID      = QColor(25, 25, 40)
C_TEXT      = QColor(220, 220, 230)
C_SCORE_BG  = QColor(25, 25, 40, 200)
C_OVERLAY   = QColor(0, 0, 0, 160)
C_GREEN     = QColor(0, 220, 120)
C_RED       = QColor(255, 80, 100)


class Direction(Enum):
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)


# ── Game Logic ───────────────────────────────────────────────────────────────

class SnakeGame:
    def __init__(self):
        self.reset()

    def reset(self):
        mid = (COLS // 2, ROWS // 2)
        self.snake = [mid, (mid[0] - 1, mid[1]), (mid[0] - 2, mid[1])]
        self.direction = Direction.RIGHT
        self.next_direction = Direction.RIGHT
        self.food = self._spawn_food()
        self.score = 0
        self.high_score = max(getattr(self, "high_score", 0), self.score)
        self.alive = True
        self.speed = 120  # ms per tick

    def _spawn_food(self):
        occupied = set(self.snake)
        while True:
            pos = (random.randint(0, COLS - 1), random.randint(0, ROWS - 1))
            if pos not in occupied:
                return pos

    def set_direction(self, d: Direction):
        opposite = {
            Direction.UP: Direction.DOWN, Direction.DOWN: Direction.UP,
            Direction.LEFT: Direction.RIGHT, Direction.RIGHT: Direction.LEFT,
        }
        if d != opposite.get(self.direction):
            self.next_direction = d

    def tick(self) -> bool:
        if not self.alive:
            return False

        self.direction = self.next_direction
        dx, dy = self.direction.value
        head = self.snake[0]
        new_head = (head[0] + dx, head[1] + dy)

        # Wall collision
        if not (0 <= new_head[0] < COLS and 0 <= new_head[1] < ROWS):
            self.alive = False
            return False

        # Self collision
        if new_head in self.snake[:-1]:
            self.alive = False
            return False

        self.snake.insert(0, new_head)

        if new_head == self.food:
            self.score += 10
            self.high_score = max(self.high_score, self.score)
            self.food = self._spawn_food()
            # Speed up every 50 points
            if self.score % 50 == 0 and self.speed > 60:
                self.speed -= 10
        else:
            self.snake.pop()

        return True


# ── Game Widget ──────────────────────────────────────────────────────────────

class GameWidget(QWidget):
    game_over = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.game = SnakeGame()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(WIDTH, HEIGHT)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self.game.speed)

    def _tick(self):
        self.game.tick()
        if not self.game.alive:
            self._timer.stop()
            self.game_over.emit()
        self.update()

    def keyPressEvent(self, e):
        key = e.key()
        mapping = {
            Qt.Key.Key_Up: Direction.UP, Qt.Key.Key_W: Direction.UP,
            Qt.Key.Key_Down: Direction.DOWN, Qt.Key.Key_S: Direction.DOWN,
            Qt.Key.Key_Left: Direction.LEFT, Qt.Key.Key_A: Direction.LEFT,
            Qt.Key.Key_Right: Direction.RIGHT, Qt.Key.Key_D: Direction.RIGHT,
        }
        if key in mapping:
            self.game.set_direction(mapping[key])
        elif key in (Qt.Key.Key_Space, Qt.Key.Key_Return):
            if not self.game.alive:
                self.game.reset()
                self._timer.start(self.game.speed)
                self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        p.fillRect(self.rect(), C_BG)

        # Grid
        p.setPen(QPen(C_GRID, 1))
        for x in range(COLS + 1):
            p.drawLine(x * CELL, 0, x * CELL, HEIGHT)
        for y in range(ROWS + 1):
            p.drawLine(0, y * CELL, WIDTH, y * CELL)

        # Food glow
        fx = self.game.food[0] * CELL + CELL / 2
        fy = self.game.food[1] * CELL + CELL / 2
        glow = QPainterPath()
        glow.addEllipse(QPointF(fx, fy), CELL * 0.9, CELL * 0.9)
        p.setBrush(QBrush(C_FOOD_GLOW))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(glow)

        # Food
        p.setBrush(QBrush(C_FOOD))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(fx, fy), CELL * 0.38, CELL * 0.38)

        # Snake body gradient (head → tail)
        n = len(self.game.snake)
        for i, (sx, sy) in enumerate(self.game.snake):
            t = i / max(n - 1, 1)
            r = int(C_SNAKE_H.red() * (1 - t) + C_SNAKE_T.red() * t)
            g = int(C_SNAKE_H.green() * (1 - t) + C_SNAKE_T.green() * t)
            b = int(C_SNAKE_H.blue() * (1 - t) + C_SNAKE_T.blue() * t)
            color = QColor(r, g, b)

            rect = QRectF(sx * CELL + 1, sy * CELL + 1, CELL - 2, CELL - 2)
            radius = 6 if i == 0 else 4
            p.setBrush(QBrush(color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, radius, radius)

        # Eyes on head
        if self.game.snake:
            hx, hy = self.game.snake[0]
            cx = hx * CELL + CELL / 2
            cy = hy * CELL + CELL / 2
            dx, dy = self.game.direction.value
            eye_off = 4
            perp_x, perp_y = -dy, dx
            for sign in (-1, 1):
                ex = cx + dx * 5 + perp_x * eye_off * sign
                ey = cy + dy * 5 + perp_y * eye_off * sign
                p.setBrush(QBrush(QColor(255, 255, 255)))
                p.drawEllipse(QPointF(ex, ey), 2.5, 2.5)

        # Score HUD
        p.setBrush(QBrush(C_SCORE_BG))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(8, 8, 160, 50), 8, 8)

        p.setPen(QPen(C_TEXT))
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(QPointF(20, 30), f"SCORE  {self.game.score}")
        p.drawText(QPointF(20, 50), f"BEST   {self.game.high_score}")

        # Game over overlay
        if not self.game.alive:
            p.fillRect(self.rect(), C_OVERLAY)
            p.setPen(QPen(C_RED))
            font_big = QFont("Segoe UI", 32, QFont.Weight.Bold)
            p.setFont(font_big)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "GAME OVER")
            font_sm = QFont("Segoe UI", 14)
            p.setFont(font_sm)
            p.setPen(QPen(C_TEXT))
            p.drawText(
                self.rect().adjusted(0, 50, 0, 50),
                Qt.AlignmentFlag.AlignCenter,
                f"Score: {self.game.score}   |   Press SPACE to restart",
            )

        p.end()


# ── Main Window ──────────────────────────────────────────────────────────────


class SnakeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Snake Game")
        self.setMinimumSize(WIDTH + 40, HEIGHT + 120)
        self.setStyleSheet(f"background-color: {C_BG.name()};")

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("SNAKE")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C_GREEN.name()}; margin-bottom: 4px;")
        layout.addWidget(title)

        # Game area
        frame = QFrame()
        frame.setStyleSheet(
            f"border: 2px solid {C_BORDER.name()}; border-radius: 8px;"
        )
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        self.game_widget = GameWidget()
        self.game_widget.game_over.connect(self._on_game_over)
        frame_layout.addWidget(self.game_widget)
        layout.addWidget(frame)

        # Controls hint
        hint = QLabel("WASD / Arrow Keys to move  |  Space to restart")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setFont(QFont("Segoe UI", 10))
        hint.setStyleSheet(f"color: {C_TEXT.name()}; opacity: 0.6; margin-top: 8px;")
        layout.addWidget(hint)

        self.game_widget.setFocus()

    def _on_game_over(self):
        pass  # overlay handles it


# ── Entry Point ──────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    win = SnakeWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
