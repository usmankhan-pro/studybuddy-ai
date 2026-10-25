import ctypes
from ctypes import wintypes
import sys
from PySide6.QtCore import QAbstractNativeEventFilter, QObject
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from config import AppConfig
from mascot import MascotWidget
from chat_window import ChatWindow

WM_HOTKEY = 0x0312
HOTKEY_ID = 101

class Win32HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.callback()
                return True, 0
        return False, 0

def create_tray_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QColor("#3182CE"))
    painter.setPen(QColor("#2C5282"))
    painter.drawRoundedRect(8, 8, 48, 48, 12, 12)
    painter.setBrush(QColor("#4FD1C5"))
    painter.drawEllipse(18, 22, 10, 10)
    painter.drawEllipse(36, 22, 10, 10)
    painter.end()
    return QIcon(pixmap)

class StudyBuddyController(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.config = AppConfig()

        initial_pos = self.config.get_mascot_pos()
        self.mascot = MascotWidget(initial_pos)
        self.chat = ChatWindow(self.config, self.mascot)

        self.mascot.clicked.connect(self.chat.toggle_visibility)
        self.mascot.position_changed.connect(self.config.set_mascot_pos)
        self.mascot.open_settings_requested.connect(self.open_settings)
        self.mascot.hide_mascot_requested.connect(self.hide_all)
        self.mascot.exit_requested.connect(self.exit_app)

        self.tray = QSystemTrayIcon(create_tray_icon(), self.app)
        _, _, hk_label = self.config.get_hotkey_modifiers_and_vk()
        self.tray.setToolTip(f"StudyBuddy AI ({hk_label} to toggle chat)")

        tray_menu = QMenu()
        show_action = tray_menu.addAction("Show Assistant")
        hide_action = tray_menu.addAction("Hide Assistant")
        settings_action = tray_menu.addAction("Settings...")
        tray_menu.addSeparator()
        exit_action = tray_menu.addAction("Exit Completely")

        show_action.triggered.connect(self.show_all)
        hide_action.triggered.connect(self.hide_all)
        settings_action.triggered.connect(self.open_settings)
        exit_action.triggered.connect(self.exit_app)

        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        self.hotkey_filter = Win32HotkeyFilter(self.chat.toggle_visibility)
        self.app.installNativeEventFilter(self.hotkey_filter)
        self.register_global_hotkey()
        self.mascot.show()

    def register_global_hotkey(self) -> None:
        if sys.platform != "win32":
            return
        try:
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
            mods, vk, label = self.config.get_hotkey_modifiers_and_vk()
            ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, mods, vk)
            self.tray.setToolTip(f"StudyBuddy AI ({label} to toggle chat)")
        except Exception:
            pass

    def open_settings(self) -> None:
        self.chat.open_settings_dialog()
        self.register_global_hotkey()

    def show_all(self) -> None:
        self.mascot.show()
        self.mascot.raise_()
        self.chat.position_near_mascot()
        self.chat.show()
        self.chat.raise_()
        self.chat.activateWindow()

    def hide_all(self) -> None:
        self.chat.hide()
        self.mascot.hide()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.mascot.isVisible() or self.chat.isVisible():
                self.chat.toggle_visibility()
            else:
                self.show_all()

    def exit_app(self) -> None:
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
            except Exception:
                pass
        self.config.set_mascot_pos(self.mascot.pos())
        self.tray.hide()
        self.app.quit()

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    controller = StudyBuddyController(app)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
