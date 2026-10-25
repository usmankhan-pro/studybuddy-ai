import html
import re
import tempfile
from datetime import date
from pathlib import Path
from PySide6.QtCore import QEasingCurve, QPoint, QRect, QPropertyAnimation, QEvent, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextBrowser,
    QPushButton,
    QLabel,
    QFileDialog,
    QMessageBox,
    QDialog,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QFrame,
    QMenu,
    QLineEdit,
    QSizeGrip,
)
from google.genai import types
import markdown

from config import AppConfig
from database import init_db, save_message, load_recent_messages, clear_all_history
from gemini_worker import GeminiWorker
from tools import TOOL_METADATA, list_approved_folder


def format_markdown_to_html(raw_text: str) -> str:
    parser = markdown.Markdown(
        extensions=["fenced_code", "tables", "codehilite", "sane_lists"],
        extension_configs={
            "codehilite": {
                "noclasses": True,
                "pygments_style": "monokai",
                "css_class": "codehilite",
            },
        },
    )
    rendered = parser.convert(html.escape(raw_text, quote=False))
    rendered = re.sub(
        r"<hr\s*/?>",
        '<hr style="border: 0; border-top: 1px solid #37393B; margin: 12px 0;">',
        rendered,
    )
    rendered = re.sub(
        r'<div class="codehilite"(?: style="[^"]*")?>',
        '<div class="codehilite" style="background-color:#1E1F20; border:1px solid #333537; '
        'border-radius:8px; margin:8px 0; overflow:hidden;">',
        rendered,
    )
    languages = re.findall(r"(?m)^```([^\n`]*)\s*$", raw_text)
    language_index = 0

    def add_code_header(match):
        nonlocal language_index
        language = languages[language_index].strip() if language_index < len(languages) else ""
        language_index += 1
        label = html.escape(language.upper() or "CODE")
        return (
            match.group(0)
            + f'<div style="background-color:#282A2C; color:#8E918F; padding:6px 10px; '
            f'font-family:Segoe UI,sans-serif; font-size:10px; font-weight:600;">{label}</div>'
        )

    rendered = re.sub(
        r'<div class="codehilite" style="[^"]*">',
        add_code_header,
        rendered,
    )
    rendered = re.sub(
        r"<pre(?: style=\"[^\"]*\")?>",
        '<pre style="margin:0; background:#1E1F20; color:#E3E3E3; border:0; padding:10px; '
        'font-family:\'Cascadia Code\',Consolas,monospace; font-size:12px; white-space:pre-wrap;">',
        rendered,
    )
    rendered = rendered.replace(
        "<table>",
        '<table style="border-collapse:collapse; margin:8px 0;">',
    ).replace(
        "<th>",
        '<th style="border:1px solid #333537; padding:4px 7px; color:#FFFFFF;">',
    ).replace(
        "<td>",
        '<td style="border:1px solid #333537; padding:4px 7px;">',
    )
    rendered = re.sub(
        r'(<span style="color: )#[0-9A-Fa-f]{6}',
        r'\1#E3E3E3',
        rendered,
    )
    return rendered

class ToolApprovalDialog(QDialog):
    def __init__(self, proposal: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Approve Tool Action")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<b>Proposed Action:</b> {proposal['title']} (<code>{proposal['name']}</code>)"))
        layout.addWidget(QLabel(f"<b>Why:</b> {proposal['why']}"))
        layout.addWidget(QLabel(f"<b>What it will do:</b> {proposal['effect']}"))

        args_str = ", ".join(f"{k}={repr(v)}" for k, v in proposal.get("args", {}).items()) or "None"
        layout.addWidget(QLabel(f"<b>Arguments:</b> <code>{args_str}</code>"))

        btn_row = QHBoxLayout()
        approve_btn = QPushButton("Approve & Run")
        approve_btn.setStyleSheet("background-color: #37393B; color: #E3E3E3; font-weight: bold; padding: 6px 12px;")
        deny_btn = QPushButton("Deny")
        approve_btn.clicked.connect(self.accept)
        deny_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(deny_btn)
        btn_row.addWidget(approve_btn)
        layout.addLayout(btn_row)

class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        win_group = QGroupBox("Windows Integration")
        w_layout = QVBoxLayout(win_group)
        self.startup_cb = QCheckBox("Launch StudyBuddy AI when I sign in to Windows")
        self.startup_cb.setChecked(self.config.is_startup_enabled())
        w_layout.addWidget(self.startup_cb)

        hk_row = QHBoxLayout()
        hk_row.addWidget(QLabel("Toggle Chat Shortcut:"))
        self.hotkey_combo = QComboBox()
        self.hotkey_combo.addItems(["Alt+Shift+S", "Ctrl+Shift+S", "Alt+Shift+B"])
        _, _, label = self.config.get_hotkey_modifiers_and_vk()
        self.hotkey_combo.setCurrentText(label)
        hk_row.addWidget(self.hotkey_combo)
        w_layout.addLayout(hk_row)
        layout.addWidget(win_group)

        ctx_group = QGroupBox("Context Sharing")
        c_layout = QVBoxLayout(ctx_group)
        self.ctx_cb = QCheckBox("Enable screenshot and clipboard attachments")
        self.ctx_cb.setChecked(self.config.is_context_sharing_enabled())
        c_layout.addWidget(self.ctx_cb)
        layout.addWidget(ctx_group)

        tools_group = QGroupBox("Assistant Tools")
        t_layout = QVBoxLayout(tools_group)
        self.master_tools_cb = QCheckBox("Enable Assistant Tools (Master Switch)")
        self.master_tools_cb.setChecked(self.config.are_tools_enabled())
        t_layout.addWidget(self.master_tools_cb)

        disabled_set = set(self.config.get_disabled_tools())
        self.tool_cbs = {}
        for t_name, meta in TOOL_METADATA.items():
            cb = QCheckBox(f"{meta['title']} ({t_name})")
            cb.setChecked(t_name not in disabled_set)
            self.tool_cbs[t_name] = cb
            t_layout.addWidget(cb)
        layout.addWidget(tools_group)

        hist_btn = QPushButton("Clear Local Message History")
        hist_btn.clicked.connect(self._clear_history)
        layout.addWidget(hist_btn)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save Settings")
        save_btn.setStyleSheet("background-color: #37393B; color: #E3E3E3; font-weight: bold; padding: 6px 12px;")
        cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(self.save_and_close)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _clear_history(self):
        clear_all_history()
        QMessageBox.information(self, "History Cleared", "Local database chat history has been reset.")

    def save_and_close(self):
        ok, msg = self.config.set_startup_enabled(self.startup_cb.isChecked())
        if not ok:
            QMessageBox.warning(self, "Startup Notice", msg)
        self.config.set_hotkey_label(self.hotkey_combo.currentText())
        self.config.set_context_sharing_enabled(self.ctx_cb.isChecked())
        self.config.set_tools_enabled(self.master_tools_cb.isChecked())
        disabled = [name for name, cb in self.tool_cbs.items() if not cb.isChecked()]
        self.config.set_disabled_tools(disabled)
        self.accept()

class ChatWindow(QWidget):
    GREETING_TEXT = "Hello. How may I assist you today?"
    MAX_CONVERSATION_TURNS = 10

    def __init__(self, config: AppConfig, mascot_widget: QWidget):
        super().__init__()
        self.config = config
        self.mascot = mascot_widget
        self.worker: GeminiWorker | None = None
        self.staged_image_path: str | None = None
        self.staged_copied_text: str | None = None
        self.conversation_contents: list[types.Content] = []
        self._last_user_prompt: str = ""
        self._status_text = "Connecting to StudyBuddy AI"
        self._resize_edges: set[str] = set()
        self._resize_origin: QPoint | None = None
        self._resize_geometry = None
        self._drag_origin: QPoint | None = None
        self._drag_window_origin: QPoint | None = None
        self._fade_out_pending = False
        self._docked_side: str | None = None

        self.setWindowTitle("StudyBuddy AI")
        self.setMinimumSize(320, 420)
        self.resize(440, 640)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowOpacity(1.0)
        self._entrance_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self._entrance_animation.setDuration(180)
        self._entrance_animation.setStartValue(0.0)
        self._entrance_animation.setEndValue(1.0)
        self._entrance_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hide_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self._hide_animation.setDuration(180)
        self._hide_animation.setStartValue(1.0)
        self._hide_animation.setEndValue(0.0)
        self._hide_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._hide_animation.finished.connect(self._finish_animated_hide)
        self._dock_animation = QPropertyAnimation(self, b"geometry", self)
        self._dock_animation.setDuration(180)
        self._dock_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(420)
        self._status_timer.timeout.connect(self._animate_status)
        self._status_frame = 0
        init_db()
        self._build_ui()
        self.apply_config_state()
        self._load_saved_messages()

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QWidget { color: #E3E3E3; font-family: 'Segoe UI', sans-serif; font-size: 13px; }
            QFrame#panel { background-color: #131314; border: 1px solid #282A2C; border-radius: 16px; }
            QWidget#header { background-color: #1E1F20; border-bottom: 1px solid #282A2C; border-top-left-radius: 15px; border-top-right-radius: 15px; }
            QTextBrowser { background: #131314; border: none; padding: 12px 10px; selection-background-color: #5E5E5E; }
            QScrollBar:vertical { width: 5px; background: transparent; margin: 2px 0; }
            QScrollBar::handle:vertical { background: #37393B; min-height: 28px; border-radius: 2px; }
            QScrollBar::handle:vertical:hover { background: #5E5E5E; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; background: transparent; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
            QPushButton { background: #282A2C; color: #E3E3E3; border: 1px solid #333537; border-radius: 9px; padding: 6px 9px; }
            QPushButton:hover { background: #37393B; border-color: #5E5E5E; color: #FFFFFF; }
            QPushButton:pressed { background: #5E5E5E; }
            QPushButton:disabled { color: #8E918F; background: #1E1F20; }
            QLineEdit { background: transparent; color: #E3E3E3; border: none; selection-background-color: #5E5E5E; padding: 0 5px; }
            QLineEdit::placeholder { color: #8E918F; }
            QMenu { background-color: #1E1F20; color: #E3E3E3; border: 1px solid #333537; border-radius: 10px; padding: 5px; }
            QMenu::item { padding: 8px 14px; border-radius: 6px; }
            QMenu::item:selected { background-color: #37393B; }
        """)

        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(1, 1, 1, 1)
        self.panel = QFrame(self)
        self.panel.setObjectName("panel")
        window_layout.addWidget(self.panel)
        root = QVBoxLayout(self.panel)
        root.setContentsMargins(14, 12, 14, 9)
        root.setSpacing(8)

        self.header_widget = QWidget()
        self.header_widget.setObjectName("header")
        header = QHBoxLayout(self.header_widget)
        header.setContentsMargins(8, 5, 8, 6)
        header.setSpacing(5)
        title_block = QVBoxLayout()
        title_block.setSpacing(1)
        title = QLabel("StudyBuddy AI")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #E3E3E3;")
        subtitle = QLabel("Learning assistant")
        subtitle.setStyleSheet("font-size: 10px; color: #8E918F;")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block)
        header.addStretch()

        self.new_chat_btn = QPushButton("✎")
        self.new_chat_btn.setFixedSize(26, 26)
        self.new_chat_btn.setToolTip("Start a fresh conversation")
        self.new_chat_btn.clicked.connect(self.start_new_chat)
        header.addWidget(self.new_chat_btn)

        self.dock_left_btn = QPushButton("◧")
        self.dock_left_btn.setFixedSize(26, 26)
        self.dock_left_btn.setToolTip("Dock to the left side of this screen")
        self.dock_left_btn.clicked.connect(lambda: self.dock_to_side("left"))
        header.addWidget(self.dock_left_btn)

        self.dock_right_btn = QPushButton("◨")
        self.dock_right_btn.setFixedSize(26, 26)
        self.dock_right_btn.setToolTip("Dock to the right side of this screen")
        self.dock_right_btn.clicked.connect(lambda: self.dock_to_side("right"))
        header.addWidget(self.dock_right_btn)

        self.folder_btn = QPushButton("▤")
        self.folder_btn.setFixedSize(26, 26)
        self.folder_btn.setToolTip("Select a folder to inspect")
        self.folder_btn.clicked.connect(self.explicit_select_folder_tool)
        header.addWidget(self.folder_btn)

        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(26, 26)
        settings_btn.setToolTip("Settings")
        settings_btn.clicked.connect(self.open_settings_dialog)
        header.addWidget(settings_btn)

        hide_btn = QPushButton("×")
        hide_btn.setFixedSize(26, 26)
        hide_btn.setToolTip("Hide StudyBuddy")
        hide_btn.clicked.connect(self.hide_animated)
        header.addWidget(hide_btn)
        root.addWidget(self.header_widget)

        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(True)
        self.chat_display.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_display.document().setDefaultStyleSheet("""
            body { color: #E3E3E3; font-family: 'Segoe UI', sans-serif; font-size: 13px; }
            p { margin-top: 0px; margin-bottom: 10px; line-height: 1.35; color: #E3E3E3; }
            h1, h2, h3 { color: #FFFFFF; font-weight: 600; margin-top: 14px; margin-bottom: 6px; }
            h1 { font-size: 20px; }
            h2 { font-size: 17px; }
            h3 { font-size: 15px; }
            ul, ol { margin-top: 4px; margin-bottom: 10px; margin-left: 18px; padding-left: 4px; }
            li { margin-bottom: 6px; line-height: 1.35; color: #E3E3E3; }
            code { background-color: #282A2C; color: #E3E3E3; padding: 2px 5px;
                border-radius: 4px; font-family: 'Cascadia Code', Consolas, monospace; font-size: 12px; }
            pre { background-color: #1E1F20; color: #E3E3E3; border: 1px solid #333537;
                border-radius: 8px; padding: 10px; font-family: 'Cascadia Code', Consolas, monospace;
                font-size: 12px; white-space: pre-wrap; }
            .codehilite { background-color: #1E1F20; border: 1px solid #333537; border-radius: 8px;
                margin: 8px 0; }
            .codehilite pre { margin: 0; border: 0; padding: 10px; }
            a { color: #A8C7FA; }
        """)
        root.addWidget(self.chat_display, stretch=1)

        self.composer = QFrame()
        self.composer.setObjectName("composer")
        self.composer.setFixedHeight(52)
        self._set_composer_focused(False)
        composer_layout = QHBoxLayout(self.composer)
        composer_layout.setContentsMargins(8, 0, 8, 0)
        composer_layout.setSpacing(8)

        self.staging_frame = QWidget()
        self.staging_frame.setStyleSheet(
            "QWidget { background-color:#282A2C; border:1px solid #333537; border-radius:12px; }"
        )
        top_stage = QHBoxLayout(self.staging_frame)
        top_stage.setContentsMargins(8, 4, 6, 4)
        top_stage.setSpacing(7)
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(32, 26)
        self.thumbnail_label.setScaledContents(True)
        self.thumbnail_label.hide()
        top_stage.addWidget(self.thumbnail_label)

        self.staging_info_label = QLabel()
        self.staging_info_label.setStyleSheet(
            "font-size:11px; color:#E3E3E3; background:transparent; border:none;"
        )
        top_stage.addWidget(self.staging_info_label, stretch=1)

        rm_btn = QPushButton("×")
        rm_btn.setFixedSize(24, 24)
        rm_btn.setToolTip("Remove attachment")
        rm_btn.setStyleSheet(
            "QPushButton { border:none; border-radius:12px; padding:0; background:#37393B; color:#E3E3E3; }"
            "QPushButton:hover { background:#5E5E5E; }"
        )
        rm_btn.clicked.connect(self.clear_staged_context)
        top_stage.addWidget(rm_btn)
        self.staging_frame.hide()
        root.addWidget(self.staging_frame)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; color: #8E918F; padding-left: 3px;")
        self.status_label.hide()
        root.addWidget(self.status_label)

        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(34, 34)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setStyleSheet(
            "QPushButton { background:#282A2C; color:#E3E3E3; border:none; border-radius:17px; "
            "font-size:20px; padding:0; }"
            "QPushButton:hover { background:#37393B; }"
        )
        self.add_btn.setToolTip(
            "Attach a screenshot or clipboard text. Attachments are sent only when you send a message."
        )
        self.add_btn.clicked.connect(self.show_attachment_menu)
        composer_layout.addWidget(self.add_btn)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Enter a prompt here")
        self.input_field.setFixedHeight(38)
        self.input_field.setToolTip(
            "Enter your message. Attached content is shared only when you select Send."
        )
        self.input_field.returnPressed.connect(self.handle_send)
        self.input_field.textChanged.connect(self._update_send_button)
        composer_layout.addWidget(self.input_field, stretch=1)

        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(34, 34)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setToolTip("Send message")
        self.send_btn.clicked.connect(self.handle_send)
        self._update_send_button()
        composer_layout.addWidget(self.send_btn)
        root.addWidget(self.composer)

        footer = QHBoxLayout()
        privacy_label = QLabel("Attachments are shared only when you send.")
        privacy_label.setStyleSheet("font-size: 10px; color: #8E918F;")
        footer.addWidget(privacy_label)
        footer.addStretch()
        self.size_grip = QSizeGrip(self.panel)
        self.size_grip.setFixedSize(14, 14)
        self.size_grip.setStyleSheet("background: transparent;")
        footer.addWidget(self.size_grip)
        root.addLayout(footer)

        self._install_interaction_filters()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fade_out_pending = False
        self._hide_animation.stop()
        self.setWindowOpacity(0.0)
        self._entrance_animation.start()

    def hide(self) -> None:
        self.hide_animated()

    def hide_animated(self) -> None:
        if not self.isVisible() or self._fade_out_pending:
            return
        self._entrance_animation.stop()
        self._fade_out_pending = True
        self._hide_animation.setStartValue(self.windowOpacity())
        self._hide_animation.start()

    def _finish_animated_hide(self) -> None:
        if self._fade_out_pending:
            self._fade_out_pending = False
            QWidget.hide(self)

    def _install_interaction_filters(self) -> None:
        self._draggable_widgets = {self.header_widget}
        self._draggable_widgets.update(self.header_widget.findChildren(QLabel))
        for widget in [self, *self.findChildren(QWidget)]:
            widget.installEventFilter(self)
            widget.setMouseTracking(True)

    def _set_composer_focused(self, focused: bool) -> None:
        background = "#282A2C" if focused else "#1E1F20"
        self.composer.setStyleSheet(
            f"QFrame#composer {{ background-color:{background}; border:1px solid #333537; border-radius:25px; }}"
        )

    def _update_send_button(self, *_args) -> None:
        active = bool(self.input_field.text().strip())
        background = "#A8C7FA" if active else "#E3E3E3"
        self.send_btn.setStyleSheet(
            f"QPushButton {{ background-color:{background}; color:#131314; border:none; "
            "border-radius:17px; font-size:16px; font-weight:600; padding:0; }"
            "QPushButton:hover { background-color:#FFFFFF; }"
        )

    def _edge_at(self, point: QPoint) -> set[str]:
        margin = 6
        edges = set()
        if point.x() <= margin:
            edges.add("left")
        elif point.x() >= self.width() - margin:
            edges.add("right")
        if point.y() <= margin:
            edges.add("top")
        elif point.y() >= self.height() - margin:
            edges.add("bottom")
        return edges

    def _update_resize_cursor(self, edges: set[str]) -> None:
        cursor = Qt.CursorShape.ArrowCursor
        if edges in ({"left", "top"}, {"right", "bottom"}):
            cursor = Qt.CursorShape.SizeFDiagCursor
        elif edges in ({"right", "top"}, {"left", "bottom"}):
            cursor = Qt.CursorShape.SizeBDiagCursor
        elif "left" in edges or "right" in edges:
            cursor = Qt.CursorShape.SizeHorCursor
        elif "top" in edges or "bottom" in edges:
            cursor = Qt.CursorShape.SizeVerCursor
        self.setCursor(cursor)

    def eventFilter(self, watched, event) -> bool:
        event_type = event.type()
        if watched is self.input_field:
            if event_type == QEvent.Type.FocusIn:
                self._set_composer_focused(True)
            elif event_type == QEvent.Type.FocusOut:
                self._set_composer_focused(False)
        if event_type in (
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
        ):
            global_pos = event.globalPosition().toPoint()
            local_pos = self.mapFromGlobal(global_pos)

            if event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                edges = self._edge_at(local_pos)
                if edges:
                    self._resize_edges = edges
                    self._resize_origin = global_pos
                    self._resize_geometry = self.geometry()
                    return True
                if watched in self._draggable_widgets:
                    self._drag_origin = global_pos
                    self._drag_window_origin = self.pos()

            elif event_type == QEvent.Type.MouseMove:
                if self._resize_edges and self._resize_origin and self._resize_geometry:
                    self._resize_from_pointer(global_pos)
                    return True
                if self._drag_origin and self._drag_window_origin:
                    delta = global_pos - self._drag_origin
                    self.move(self._drag_window_origin + delta)
                    self._docked_side = None
                    return True
                if watched is self or self.panel.underMouse():
                    self._update_resize_cursor(self._edge_at(local_pos))

            elif event_type == QEvent.Type.MouseButtonRelease:
                self._resize_edges.clear()
                self._resize_origin = None
                self._resize_geometry = None
                self._drag_origin = None
                self._drag_window_origin = None
                self._update_resize_cursor(self._edge_at(local_pos))

        return super().eventFilter(watched, event)

    def _resize_from_pointer(self, global_pos: QPoint) -> None:
        if self._resize_origin is None or self._resize_geometry is None:
            return
        delta = global_pos - self._resize_origin
        original = self._resize_geometry
        left, top = original.left(), original.top()
        right, bottom = original.right(), original.bottom()

        if "left" in self._resize_edges:
            left = min(left + delta.x(), right - self.minimumWidth() + 1)
        elif "right" in self._resize_edges:
            right = max(right + delta.x(), left + self.minimumWidth() - 1)
        if "top" in self._resize_edges:
            top = min(top + delta.y(), bottom - self.minimumHeight() + 1)
        elif "bottom" in self._resize_edges:
            bottom = max(bottom + delta.y(), top + self.minimumHeight() - 1)
        self.setGeometry(left, top, right - left + 1, bottom - top + 1)
        self._docked_side = None

    def dock_to_side(self, side: str) -> None:
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        dock_width = min(available.width(), max(self.minimumWidth(), int(available.width() * 0.42)))
        dock_height = min(available.height(), max(self.minimumHeight(), int(available.height() * 0.85)))
        x = available.left() if side == "left" else available.right() - dock_width + 1
        y = available.top() + (available.height() - dock_height) // 2
        target = QRect(x, y, dock_width, dock_height)

        self._dock_animation.stop()
        self._docked_side = side
        if not self.isVisible():
            self.setGeometry(target)
            self.show()
            return
        opacity = QPropertyAnimation(self, b"windowOpacity", self)
        opacity.setDuration(180)
        opacity.setStartValue(self.windowOpacity())
        opacity.setKeyValueAt(0.5, 0.78)
        opacity.setEndValue(1.0)
        opacity.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._dock_animation.setStartValue(self.geometry())
        self._dock_animation.setEndValue(target)
        self._dock_animation.start()
        opacity.start()
        self._dock_opacity_animation = opacity

    def apply_config_state(self) -> None:
        enabled = self.config.is_context_sharing_enabled()
        self.add_btn.setVisible(enabled)
        if not enabled:
            self.clear_staged_context()

    def _load_saved_messages(self) -> None:
        self._append_session_date()
        messages = load_recent_messages(limit=40)
        for message in messages:
            sender = message["sender"]
            content = message["content"]
            self.append_message(
                sender,
                content,
                is_error=message["is_error"],
                save=False,
            )
            if message["is_error"]:
                continue
            if sender == "You":
                self.conversation_contents.append(
                    types.Content(role="user", parts=[types.Part.from_text(text=content)])
                )
            elif sender in ("StudyBuddy", "StudyBuddy AI"):
                self.conversation_contents.append(
                    types.Content(role="model", parts=[types.Part.from_text(text=content)])
                )
        if not messages:
            self.append_message("StudyBuddy AI", self.GREETING_TEXT, save=False)
        self.conversation_contents = self.conversation_contents[-self.MAX_CONVERSATION_TURNS * 2:]

    def _append_session_date(self) -> None:
        self.chat_display.append(
            "<div align='center' style='margin:4px 0 16px 0;'>"
            "<span style='background-color:#1E1F20; color:#8E918F; padding:4px 10px; "
            "border-radius:10px; font-size:11px;'>Today · "
            f"{date.today().strftime('%B %d, %Y')}</span></div>"
        )

    def position_near_mascot(self) -> None:
        m_pos = self.mascot.pos()
        screen = QGuiApplication.screenAt(m_pos) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()

        target_x = m_pos.x() - self.width() - 12
        if target_x < avail.left():
            target_x = m_pos.x() + self.mascot.width() + 12

        target_y = m_pos.y() + self.mascot.height() - self.height()
        target_x = max(avail.left() + 8, min(target_x, avail.right() - self.width() - 8))
        target_y = max(avail.top() + 8, min(target_y, avail.bottom() - self.height() - 8))
        self.move(QPoint(target_x, target_y))

    def toggle_visibility(self) -> None:
        if self.isVisible():
            self.hide_animated()
        else:
            self.position_near_mascot()
            self.show()
            self.raise_()
            self.activateWindow()
            self.input_field.setFocus()

    def append_message(self, sender: str, text: str, is_error: bool = False, save: bool = True) -> None:
        is_user = sender == "You"
        if is_error:
            formatted = format_markdown_to_html(text)
            entry = (
                "<div style='margin:8px 0; padding:8px 10px; color:#FCA5A5; "
                "background-color:#3F1D2E; border-radius:9px;'>"
                f"<b>Notice</b><br>{formatted}</div>"
            )
        elif is_user:
            formatted = format_markdown_to_html(text)
            entry = (
                "<table width='100%' cellspacing='0' cellpadding='0' style='margin:8px 0;'>"
                "<tr><td align='right'>"
                "<table cellspacing='0' cellpadding='0' style='background-color:#282A2C; border-radius:20px;'>"
                "<tr><td style='padding:9px 14px; color:#E3E3E3; font-family:Segoe UI,sans-serif; "
                f"font-size:13px; line-height:1.5;'>{formatted}</td></tr>"
                "</table></td></tr></table>"
            )
        else:
            formatted = format_markdown_to_html(text)
            entry = (
                "<table width='100%' cellspacing='0' cellpadding='0' style='margin:12px 0 18px 0;'>"
                "<tr><td width='24' valign='top'>"
                "<span style='color:#8E918F; font-size:17px; font-weight:bold;'>✦</span>"
                "</td><td>"
                "<div style='font-family:Segoe UI,sans-serif; font-size:13px; color:#E3E3E3; "
                f"line-height:1.75;'>{formatted}</div>"
                "</td></tr></table>"
            )
        self.chat_display.append(entry)
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )
        if save:
            save_message(sender, text, is_error)

    def start_new_chat(self) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.information(
                self,
                "Response in Progress",
                "Please wait for the current response to finish before starting a new conversation.",
            )
            return
        self.conversation_contents.clear()
        self._last_user_prompt = ""
        self.clear_staged_context()
        self.chat_display.clear()
        clear_all_history()
        self._append_session_date()
        self.append_message("StudyBuddy AI", self.GREETING_TEXT, save=False)
        self.input_field.clear()
        self.input_field.setFocus()

    def _animate_status(self) -> None:
        self._status_frame = (self._status_frame + 1) % 4
        self.status_label.setText(self._status_text + "." * self._status_frame)

    def _set_worker_status(self, text: str) -> None:
        self._status_text = text.rstrip(".")
        self._status_frame = 0
        self._animate_status()

    def show_attachment_menu(self) -> None:
        if not self.config.is_context_sharing_enabled():
            QMessageBox.information(
                self,
                "Attachments Disabled",
                "Enable context sharing in Settings to attach screenshots or clipboard text.",
            )
            return
        menu = QMenu(self)
        capture_action = menu.addAction("📷  Capture or upload screenshot")
        text_action = menu.addAction("📋  Paste copied text")
        chosen = menu.exec(self.add_btn.mapToGlobal(QPoint(0, -menu.sizeHint().height())))
        if chosen == capture_action:
            self.handle_share_screenshot()
        elif chosen == text_action:
            self.handle_paste_copied_text()

    def _show_attachment_chip(self, text: str, pixmap: QPixmap | None = None) -> None:
        self.staging_info_label.setText(text)
        if pixmap is not None and not pixmap.isNull():
            self.thumbnail_label.setPixmap(pixmap)
            self.thumbnail_label.show()
        else:
            self.thumbnail_label.clear()
            self.thumbnail_label.hide()
        self.staging_frame.show()

    def handle_share_screenshot(self) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle("Add Screenshot")
        msg.setText("Capture your screen or select an image to attach.")
        capture_btn = msg.addButton("Capture screen", QMessageBox.ButtonRole.ActionRole)
        browse_btn = msg.addButton("Upload image", QMessageBox.ButtonRole.ActionRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == capture_btn:
            was_m_vis = self.mascot.isVisible()
            QWidget.hide(self)
            self.mascot.hide()
            QGuiApplication.processEvents()

            screen = QGuiApplication.screenAt(self.mascot.pos()) or QGuiApplication.primaryScreen()
            pixmap = screen.grabWindow(0)

            if was_m_vis:
                self.mascot.show()
            QWidget.show(self)

            tmp = Path(tempfile.gettempdir()) / "studybuddy_capture.png"
            if not pixmap.save(str(tmp), "PNG"):
                QMessageBox.warning(self, "Screenshot Failed", "The screenshot could not be saved.")
                return
            self.staged_image_path = str(tmp)
            self.staged_copied_text = None
            self._show_attachment_chip(f"Screenshot · {tmp.name}", pixmap)
        elif clicked == browse_btn:
            path, _ = QFileDialog.getOpenFileName(self, "Open Image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
            if path:
                self.staged_image_path = path
                self.staged_copied_text = None
                self._show_attachment_chip(f"Image · {Path(path).name}", QPixmap(path))

    def handle_paste_copied_text(self) -> None:
        text = QGuiApplication.clipboard().text().strip()
        if not text:
            QMessageBox.information(self, "Clipboard Empty", "Your clipboard contains no text to share.")
            return
        self.staged_copied_text = text
        snippet = text[:54].replace("\n", " ") + ("…" if len(text) > 54 else "")
        self.staged_image_path = None
        self._show_attachment_chip(f"Text · {snippet}")

    def clear_staged_context(self) -> None:
        self.staged_image_path = None
        self.staged_copied_text = None
        self.thumbnail_label.clear()
        self.thumbnail_label.hide()
        self.staging_info_label.clear()
        self.staging_frame.hide()

    def explicit_select_folder_tool(self) -> None:
        if not self.config.are_tools_enabled():
            QMessageBox.information(self, "Tools Disabled", "Tools are currently disabled in Settings.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to List")
        if folder:
            res = list_approved_folder(folder)
            if res.get("status") == "ok":
                names = ", ".join(item["name"] for item in res["items"][:20])
                self.append_message("StudyBuddy (Folder Tool)", f"Listed items in {res['folder']}:\n{names}")
            else:
                self.append_message("System", res.get("error", "Error"), is_error=True)

    def handle_send(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        user_text = self.input_field.text().strip()
        if not user_text and not self.staged_image_path and not self.staged_copied_text:
            self.status_label.setText("Please enter a message or attach content first.")
            self.status_label.show()
            return

        if not user_text:
            user_text = "Please analyze the shared content and provide troubleshooting steps."

        self._last_user_prompt = user_text
        notes = []
        if self.staged_image_path:
            notes.append("[Screenshot]")
        if self.staged_copied_text:
            notes.append("[Copied Text]")
        prefix = (" ".join(notes) + "\n") if notes else ""
        self.append_message("You", prefix + user_text)

        self.input_field.clear()
        self.input_field.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.mascot.set_thinking(True)
        self._status_text = "Connecting to StudyBuddy AI"
        self._status_frame = 0
        self._status_timer.start()
        self._animate_status()
        self.status_label.show()

        if len(self.conversation_contents) > self.MAX_CONVERSATION_TURNS * 2:
            self.conversation_contents = self.conversation_contents[-(self.MAX_CONVERSATION_TURNS * 2):]

        self.worker = GeminiWorker(
            history=self.conversation_contents,
            user_text=user_text,
            image_path=self.staged_image_path,
            copied_snippet=self.staged_copied_text,
            tools_enabled=self.config.are_tools_enabled(),
            disabled_tools=self.config.get_disabled_tools(),
        )
        self.worker.status_update.connect(self._set_worker_status)
        self.worker.response_ready.connect(self._on_worker_response)
        self.worker.error_occurred.connect(lambda err: self.append_message("System Notice", err, is_error=True))
        self.worker.tool_approval_requested.connect(self._on_tool_approval_requested)
        self.worker.tool_executed_log.connect(lambda l: self.append_message("Tool Log", l))
        self.worker.finished.connect(self._on_worker_finished)

        self.clear_staged_context()
        self.worker.start()

    def _on_tool_approval_requested(self, proposal: dict) -> None:
        dlg = ToolApprovalDialog(proposal, self)
        approved = dlg.exec() == QDialog.DialogCode.Accepted
        if self.worker:
            self.worker.set_tool_approval_decision(approved)

    def _on_worker_response(self, reply: str, model_content: object) -> None:
        self.append_message("StudyBuddy", reply)
        self.conversation_contents.append(
            types.Content(role="user", parts=[types.Part.from_text(text=self._last_user_prompt)])
        )
        if model_content:
            self.conversation_contents.append(model_content)
        else:
            self.conversation_contents.append(
                types.Content(role="model", parts=[types.Part.from_text(text=reply)])
            )

    def _on_worker_finished(self) -> None:
        self._status_timer.stop()
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.mascot.set_thinking(False)
        self.status_label.hide()
        self.input_field.setFocus()

    def open_settings_dialog(self) -> None:
        dlg = SettingsDialog(self.config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.apply_config_state()
