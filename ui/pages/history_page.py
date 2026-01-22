from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from ui.widgets.card import Card


class HistoryPage(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(18)

        history_card = Card("注文履歴")
        layout.addWidget(history_card)

        helper = QLabel("ログは時系列で追記されます。")
        helper.setObjectName("mutedLabel")
        history_card.body.addWidget(helper)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("ログ出力がここに表示されます")
        history_card.body.addWidget(self.log_view)

        layout.addStretch()

    def append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)