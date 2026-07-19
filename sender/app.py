"""Sender GUI (PyQt6).

A modern window where you paste or type code, then click Send. The text is
pushed to the receiver exactly as entered (indentation, comments, and all
whitespace preserved). The receiver stores it until you press the type hotkey
on the target machine.

Network calls run on a background thread pool so the UI never freezes.

Run:
    python -m sender.app
"""

from __future__ import annotations

import sys
from datetime import datetime

from PyQt6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from sender import settings
from sender.client import (
    abort_type,
    base_url,
    check_health,
    get_clipboard_history,
    get_latest,
    send_text,
    set_endpoint,
    trigger_type,
)


# ---------------------------------------------------------------------------
# Background task plumbing (keep network off the UI thread)
# ---------------------------------------------------------------------------
class _TaskSignals(QObject):
    finished = pyqtSignal(bool, str)  # (ok, message)


class _Task(QRunnable):
    """Runs a callable that returns a status string; reports ok/message."""

    def __init__(self, fn) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _TaskSignals()

    def run(self) -> None:  # noqa: D401
        try:
            message = self.fn()
            self.signals.finished.emit(True, message)
        except Exception as exc:  # noqa: BLE001
            self.signals.finished.emit(False, str(exc))


class _DataSignals(QObject):
    finished = pyqtSignal(bool, str, object)  # (ok, message, data)


class _DataTask(QRunnable):
    """Runs a callable that returns arbitrary data; reports ok/message/data."""

    def __init__(self, fn) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _DataSignals()

    def run(self) -> None:  # noqa: D401
        try:
            data = self.fn()
            self.signals.finished.emit(True, "ok", data)
        except Exception as exc:  # noqa: BLE001
            self.signals.finished.emit(False, str(exc), None)


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
_STYLESHEET = """
QMainWindow, QWidget { background-color: #1e1e2e; color: #cdd6f4; }
QLabel#title { font-size: 13px; color: #a6adc8; }
QLabel#status { font-size: 12px; }
QPlainTextEdit {
    background-color: #11111b;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 8px;
    padding: 8px;
    selection-background-color: #585b70;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-size: 13px;
}
QPushButton:hover { background-color: #45475a; }
QPushButton:pressed { background-color: #585b70; }
QLineEdit {
    background-color: #11111b;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: #585b70;
}
QLineEdit:focus { border: 1px solid #89b4fa; }
QPushButton#send {
    background-color: #89b4fa;
    color: #11111b;
    font-weight: 600;
}
QPushButton#send:hover { background-color: #74a8fc; }
QPushButton#send:pressed { background-color: #5c94f7; }
"""


class ReceivedDialog(QDialog):
    """Read-only viewer showing exactly what the receiver currently holds."""

    def __init__(self, info: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Data on Receiver")
        self.resize(680, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        ts = info.get("received_at")
        when = (
            datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(ts, (int, float))
            else "unknown"
        )
        header = QLabel(f"{info.get('chars', 0)} chars   ·   received {when}")
        header.setObjectName("title")
        layout.addWidget(header)

        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        viewer.setFont(font)
        viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        viewer.setPlainText(info.get("text", ""))
        layout.addWidget(viewer, 1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)


class ClipboardHistoryDialog(QDialog):
    """Live, scrolling history of clipboard entries received from the receiver.

    Newest entries appear at the top. Selecting one shows its full text; older
    entries are never removed by newer ones arriving.
    """

    def __init__(self, history: list, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Clipboard History (from receiver)")
        self.resize(760, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.count_label = QLabel("")
        self.count_label.setObjectName("title")
        layout.addWidget(self.count_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_select)
        splitter.addWidget(self.list)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.detail.setFont(font)
        self.detail.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        splitter.addWidget(self.detail)
        splitter.setSizes([300, 460])
        layout.addWidget(splitter, 1)

        row = QHBoxLayout()
        self.copy_btn = QPushButton("Copy to my clipboard")
        self.copy_btn.clicked.connect(self._on_copy)
        row.addWidget(self.copy_btn)
        row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        layout.addLayout(row)

        # Seed with existing history (oldest -> newest; we insert at top).
        for entry in history:
            self._insert(entry)
        self._update_count()

    def _insert(self, entry: dict) -> None:
        ts = entry.get("ts")
        when = (
            datetime.fromtimestamp(ts).strftime("%H:%M:%S")
            if isinstance(ts, (int, float))
            else "??:??:??"
        )
        text = entry.get("text", "")
        first_line = text.strip().splitlines()[0] if text.strip() else "(empty)"
        preview = (first_line[:60] + "…") if len(first_line) > 60 else first_line
        item = QListWidgetItem(f"[{when}]  {preview}")
        item.setData(Qt.ItemDataRole.UserRole, text)
        self.list.insertItem(0, item)  # newest on top

    def add_entries(self, entries: list) -> None:
        for entry in entries:
            self._insert(entry)
        self._update_count()

    def _update_count(self) -> None:
        self.count_label.setText(f"{self.list.count()} entr{'y' if self.list.count() == 1 else 'ies'}")

    def _on_select(self, current, _previous) -> None:
        if current is not None:
            self.detail.setPlainText(current.data(Qt.ItemDataRole.UserRole) or "")

    def _on_copy(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            QApplication.clipboard().setText(item.data(Qt.ItemDataRole.UserRole) or "")


class SenderWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Keyboard Sender")
        self.resize(760, 560)

        self.pool = QThreadPool.globalInstance()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # -- connection bar ---------------------------------------------
        # Lets you point the sender at the receiver's address (LAN IP,
        # Tailscale IP, or 127.0.0.1 for local testing) without editing code.
        cfg = settings.load()
        set_endpoint(cfg["host"], cfg["port"], cfg["token"])

        conn = QHBoxLayout()
        conn.addWidget(QLabel("Receiver"))
        self.host_edit = QLineEdit(str(cfg["host"]))
        self.host_edit.setPlaceholderText("host / IP (e.g. 100.x.y.z)")
        self.port_edit = QLineEdit(str(cfg["port"]))
        self.port_edit.setFixedWidth(70)
        self.port_edit.setPlaceholderText("port")
        conn.addWidget(self.host_edit, 1)
        conn.addWidget(QLabel(":"))
        conn.addWidget(self.port_edit)
        conn.addWidget(QLabel("Token"))
        self.token_edit = QLineEdit(str(cfg["token"]))
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        conn.addWidget(self.token_edit, 1)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self.on_apply_endpoint)
        conn.addWidget(self.apply_btn)
        root.addLayout(conn)

        # -- status line -------------------------------------------------
        top = QHBoxLayout()
        self.target_label = QLabel(f"Target: {base_url()}")
        self.target_label.setObjectName("title")
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        top.addWidget(self.target_label)
        top.addStretch(1)
        top.addWidget(self.status)
        root.addLayout(top)

        # -- code editor -------------------------------------------------
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Paste or type code here ...")
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(font)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setTabStopDistance(4 * self.editor.fontMetrics().horizontalAdvance(" "))
        root.addWidget(self.editor, 1)

        # -- buttons -----------------------------------------------------
        bottom = QHBoxLayout()
        self.check_btn = QPushButton("Check Receiver")
        self.view_btn = QPushButton("View Received")
        self.clip_btn = QPushButton("Clipboard History")
        self.clear_btn = QPushButton("Clear")
        self.abort_btn = QPushButton("Abort")
        self.send_btn = QPushButton("Send")
        self.type_btn = QPushButton("Type on Receiver")
        self.type_btn.setObjectName("send")  # primary (blue) accent
        self.type_btn.setDefault(True)

        self.check_btn.clicked.connect(self.on_check)
        self.view_btn.clicked.connect(self.on_view)
        self.clip_btn.clicked.connect(self.on_clipboard_history)
        self.clear_btn.clicked.connect(self.on_clear)
        self.abort_btn.clicked.connect(self.on_abort)
        self.send_btn.clicked.connect(self.on_send)
        self.type_btn.clicked.connect(self.on_type)

        bottom.addWidget(self.check_btn)
        bottom.addWidget(self.view_btn)
        bottom.addWidget(self.clip_btn)
        bottom.addWidget(self.clear_btn)
        bottom.addStretch(1)
        bottom.addWidget(self.abort_btn)
        bottom.addWidget(self.send_btn)
        bottom.addWidget(self.type_btn)
        root.addLayout(bottom)

        # -- clipboard history state + polling --------------------------
        self._clip_history: list = []
        self._clip_last_id = 0
        self._clip_unread = 0
        self._clip_polling = False
        self._clip_dialog: ClipboardHistoryDialog | None = None

        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        )
        self.tray.setToolTip("Keyboard Sender")
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

        self.clip_timer = QTimer(self)
        self.clip_timer.setInterval(3000)  # poll receiver clipboard every 3s
        self.clip_timer.timeout.connect(self._poll_clipboard)
        self.clip_timer.start()

    # -- helpers ---------------------------------------------------------
    def _set_status(self, msg: str, ok: bool = True) -> None:
        self.status.setText(msg)
        self.status.setStyleSheet(f"color: {'#a6e3a1' if ok else '#f38ba8'};")

    def _set_busy(self, busy: bool) -> None:
        for b in (
            self.check_btn,
            self.view_btn,
            self.clear_btn,
            self.abort_btn,
            self.send_btn,
            self.type_btn,
        ):
            b.setEnabled(not busy)

    def _run(self, fn) -> None:
        self._set_busy(True)
        task = _Task(fn)
        task.signals.finished.connect(self._on_task_done)
        self.pool.start(task)

    def _on_task_done(self, ok: bool, message: str) -> None:
        self._set_busy(False)
        self._set_status(message, ok=ok)

    # -- actions ---------------------------------------------------------
    def on_apply_endpoint(self) -> None:
        """Repoint the sender at the entered receiver address + token."""
        host = self.host_edit.text().strip()
        if not host:
            self._set_status("host cannot be empty", ok=False)
            return
        try:
            port = int(self.port_edit.text().strip())
        except ValueError:
            self._set_status("port must be a number", ok=False)
            return
        token = self.token_edit.text()
        set_endpoint(host, port, token)
        settings.save(host, port, token)
        self.target_label.setText(f"Target: {base_url()}")
        self._set_status("endpoint updated", ok=True)

    def on_check(self) -> None:
        self._set_status("checking ...", ok=True)

        def task() -> str:
            info = check_health()
            return f"online (payload chars: {info.get('chars', 0)})"

        self._run(task)

    def on_clear(self) -> None:
        self.editor.clear()
        self._set_status("cleared", ok=True)

    def on_send(self) -> None:
        content = self.editor.toPlainText()
        if not content:
            self._set_status("nothing to send", ok=False)
            return
        self._set_status("sending ...", ok=True)

        def task() -> str:
            info = send_text(content)
            return f"sent {info.get('chars', 0)} chars"

        self._run(task)

    def on_type(self) -> None:
        """Send the current text (if any) and start typing on the receiver.

        If the editor is empty, the receiver types whatever was last sent.
        There's a countdown on the receiver so you can focus the target window.
        """
        content = self.editor.toPlainText()
        self._set_status("starting type ...", ok=True)

        def task() -> str:
            info = trigger_type(text=content or None)
            delay = info.get("start_delay", 0)
            return f"typing on receiver (focus target within {delay:g}s)"

        self._run(task)

    def on_abort(self) -> None:
        self._set_status("aborting ...", ok=True)

        def task() -> str:
            info = abort_type()
            return "aborted" if info.get("status") == "aborted" else "nothing to abort"

        self._run(task)

    def on_view(self) -> None:
        """Fetch and display what the receiver currently holds."""
        self._set_status("fetching received ...", ok=True)
        self._set_busy(True)
        task = _DataTask(get_latest)
        task.signals.finished.connect(self._on_latest)
        self.pool.start(task)

    def _on_latest(self, ok: bool, message: str, data: object) -> None:
        self._set_busy(False)
        if not ok:
            self._set_status(message, ok=False)
            return
        info = data if isinstance(data, dict) else {}
        if not info.get("has_payload"):
            self._set_status("receiver holds nothing yet", ok=False)
            return
        self._set_status(f"receiver holds {info.get('chars', 0)} chars", ok=True)
        ReceivedDialog(info, self).exec()

    # -- clipboard history ----------------------------------------------
    def _poll_clipboard(self) -> None:
        """Every 3s, pull any new clipboard entries from the receiver."""
        if self._clip_polling:
            return
        self._clip_polling = True
        since = self._clip_last_id
        task = _DataTask(lambda: get_clipboard_history(since=since))
        task.signals.finished.connect(self._on_clipboard_result)
        self.pool.start(task)

    def _on_clipboard_result(self, ok: bool, message: str, data: object) -> None:
        self._clip_polling = False
        if not ok:
            # Stay quiet on poll errors (receiver may be offline); don't spam.
            return
        info = data if isinstance(data, dict) else {}
        entries = info.get("entries") or []
        if "last_id" in info:
            self._clip_last_id = max(self._clip_last_id, int(info["last_id"]))
        if not entries:
            return

        self._clip_history.extend(entries)
        # Keep an existing dialog in sync whether it's visible or not, so it's
        # current when reopened.
        if self._clip_dialog is not None:
            self._clip_dialog.add_entries(entries)
        if self._clip_dialog is None or not self._clip_dialog.isVisible():
            self._clip_unread += len(entries)
        self._update_clip_button()

        n = len(entries)
        self._set_status(f"received {n} new clipboard item{'s' if n != 1 else ''}", ok=True)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.showMessage(
                "Keyboard Sender",
                f"Received new clipboard information ({n} new)",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    def _update_clip_button(self) -> None:
        if self._clip_unread > 0:
            self.clip_btn.setText(f"Clipboard History ({self._clip_unread})")
        else:
            self.clip_btn.setText("Clipboard History")

    def on_clipboard_history(self) -> None:
        self._clip_unread = 0
        self._update_clip_button()
        if self._clip_dialog is None:
            self._clip_dialog = ClipboardHistoryDialog(self._clip_history, self)
        self._clip_dialog.show()
        self._clip_dialog.raise_()
        self._clip_dialog.activateWindow()


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(_STYLESHEET)
    window = SenderWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
