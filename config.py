import os
import sys
import winreg
from pathlib import Path
from dotenv import load_dotenv
from PySide6.QtCore import QSettings, QPoint, QRect
from PySide6.QtGui import QGuiApplication

APP_NAME = "StudyBuddyAI"
ORG_NAME = "StudyBuddyProject"
RUN_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

load_dotenv(get_base_dir() / ".env")

class AppConfig:
    def __init__(self):
        self.settings = QSettings(ORG_NAME, APP_NAME)

    def get_mascot_pos(self, mascot_width: int = 90, mascot_height: int = 90) -> QPoint:
        saved_x = self.settings.value("mascot/x", None, type=int)
        saved_y = self.settings.value("mascot/y", None, type=int)
        screens = QGuiApplication.screens()
        if not screens:
            return QPoint(100, 100)
        if saved_x is not None and saved_y is not None:
            cand = QRect(saved_x, saved_y, mascot_width, mascot_height)
            for scr in screens:
                if scr.availableGeometry().intersects(cand):
                    avail = scr.availableGeometry()
                    return QPoint(
                        max(avail.left(), min(saved_x, avail.right() - mascot_width)),
                        max(avail.top(), min(saved_y, avail.bottom() - mascot_height))
                    )
        primary = QGuiApplication.primaryScreen().availableGeometry()
        return QPoint(primary.right() - mascot_width - 30, primary.bottom() - mascot_height - 40)

    def set_mascot_pos(self, pos: QPoint) -> None:
        self.settings.setValue("mascot/x", pos.x())
        self.settings.setValue("mascot/y", pos.y())

    def is_context_sharing_enabled(self) -> bool:
        return self.settings.value("features/context_sharing", True, type=bool)

    def set_context_sharing_enabled(self, enabled: bool) -> None:
        self.settings.setValue("features/context_sharing", enabled)

    def are_tools_enabled(self) -> bool:
        return self.settings.value("features/tools_enabled", True, type=bool)

    def set_tools_enabled(self, enabled: bool) -> None:
        self.settings.setValue("features/tools_enabled", enabled)

    def get_disabled_tools(self) -> list[str]:
        val = self.settings.value("features/disabled_tools", "")
        return [t.strip() for t in val.split(",") if t.strip()]

    def set_disabled_tools(self, tool_names: list[str]) -> None:
        self.settings.setValue("features/disabled_tools", ",".join(tool_names))

    def get_hotkey_modifiers_and_vk(self) -> tuple[int, int, str]:
        label = self.settings.value("shortcuts/toggle_chat", "Alt+Shift+S", type=str)
        if label == "Ctrl+Shift+S":
            return (0x0002 | 0x0004, ord("S"), "Ctrl+Shift+S")
        elif label == "Alt+Shift+B":
            return (0x0001 | 0x0004, ord("B"), "Alt+Shift+B")
        return (0x0001 | 0x0004, ord("S"), "Alt+Shift+S")

    def set_hotkey_label(self, label: str) -> None:
        self.settings.setValue("shortcuts/toggle_chat", label)

    def is_startup_enabled(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REGISTRY_PATH, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, APP_NAME)
                return True
        except (FileNotFoundError, OSError):
            return False

    def set_startup_enabled(self, enabled: bool) -> tuple[bool, str]:
        if sys.platform != "win32":
            return False, "Windows registry startup is only supported on Windows."
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REGISTRY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    if getattr(sys, "frozen", False):
                        cmd = f'"{sys.executable}"'
                    else:
                        pythonw = Path(sys.executable).with_name("pythonw.exe")
                        exe_to_use = pythonw if pythonw.exists() else Path(sys.executable)
                        main_script = get_base_dir() / "main.py"
                        cmd = f'"{exe_to_use}" "{main_script}"'
                    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                    return True, "Launch at Windows sign-in enabled."
                else:
                    try:
                        winreg.DeleteValue(key, APP_NAME)
                    except FileNotFoundError:
                        pass
                    return True, "Launch at Windows sign-in disabled."
        except OSError as e:
            return False, f"Failed to update Windows startup registry: {e}"
