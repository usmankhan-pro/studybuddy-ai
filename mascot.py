from PySide6.QtCore import Qt, QPoint, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient
from PySide6.QtWidgets import QWidget, QMenu

class MascotWidget(QWidget):
    clicked = Signal()
    position_changed = Signal(QPoint)
    open_settings_requested = Signal()
    hide_mascot_requested = Signal()
    exit_requested = Signal()

    MASCOT_SIZE = 90
    CLICK_DRAG_THRESHOLD = 6

    def __init__(self, initial_pos: QPoint):
        super().__init__()
        self.setFixedSize(self.MASCOT_SIZE, self.MASCOT_SIZE)
        self.move(initial_pos)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("StudyBuddy AI")
        self._press_global_pos = None
        self._window_start_pos = None
        self._is_dragging = False
        self._is_thinking = False

    def set_thinking(self, thinking: bool) -> None:
        self._is_thinking = thinking
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 45))
        painter.drawEllipse(QRectF(18, 74, 54, 10))

        painter.setPen(QPen(QColor("#4A5568"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(45, 20, 45, 8)
        orb_color = QColor("#F6AD55") if self._is_thinking else QColor("#38B2AC")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(orb_color)
        painter.drawEllipse(QRectF(39, 3, 12, 12))

        painter.setBrush(QColor("#2B6CB0"))
        painter.drawRoundedRect(QRectF(8, 34, 8, 22), 4, 4)
        painter.drawRoundedRect(QRectF(74, 34, 8, 22), 4, 4)

        grad = QLinearGradient(14, 18, 76, 72)
        grad.setColorAt(0.0, QColor("#63B3ED"))
        grad.setColorAt(1.0, QColor("#3182CE"))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor("#2C5282"), 2))
        painter.drawRoundedRect(QRectF(14, 18, 62, 54), 16, 16)

        painter.setBrush(QColor("#1A202C"))
        painter.setPen(QPen(QColor("#2D3748"), 1.5))
        painter.drawRoundedRect(QRectF(21, 26, 48, 36), 10, 10)

        eye_color = QColor("#FBD38D") if self._is_thinking else QColor("#4FD1C5")
        painter.setBrush(eye_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(29, 35, 10, 11))
        painter.drawEllipse(QRectF(51, 35, 10, 11))

        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(31, 37, 3.5, 3.5))
        painter.drawEllipse(QRectF(53, 37, 3.5, 3.5))

        painter.setPen(QPen(eye_color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(QRectF(35, 44, 20, 12), 200 * 16, 140 * 16)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global_pos = event.globalPosition().toPoint()
            self._window_start_pos = self.pos()
            self._is_dragging = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._press_global_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            delta = event.globalPosition().toPoint() - self._press_global_pos
            if delta.manhattanLength() >= self.CLICK_DRAG_THRESHOLD:
                self._is_dragging = True
                self.move(self._window_start_pos + delta)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            if self._is_dragging:
                self.position_changed.emit(self.pos())
            else:
                self.clicked.emit()
            self._press_global_pos = None
            self._window_start_pos = None
            self._is_dragging = False
            event.accept()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        toggle_action = menu.addAction("Open / Hide Chat")
        settings_action = menu.addAction("Settings...")
        hide_action = menu.addAction("Hide Mascot to Tray")
        menu.addSeparator()
        exit_action = menu.addAction("Exit StudyBuddy AI")

        chosen = menu.exec(event.globalPos())
        if chosen == toggle_action:
            self.clicked.emit()
        elif chosen == settings_action:
            self.open_settings_requested.emit()
        elif chosen == hide_action:
            self.hide_mascot_requested.emit()
        elif chosen == exit_action:
            self.exit_requested.emit()
