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

        error_card = Card("エラー詳細")
        layout.addWidget(error_card)

        error_helper = QLabel("エラー時の詳細はここに記録されます。")
        error_helper.setObjectName("mutedLabel")
        error_card.body.addWidget(error_helper)

        self.error_view = QPlainTextEdit()
        self.error_view.setReadOnly(True)
        self.error_view.setPlaceholderText("エラー詳細がここに表示されます")
        error_card.body.addWidget(self.error_view)
        
        layout.addStretch()

    def append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)