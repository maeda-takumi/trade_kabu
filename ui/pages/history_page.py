from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.widgets.card import Card


class HistoryPage(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(18)

        history_card = Card("注文履歴")
        layout.addWidget(history_card)

        placeholder = QLabel("履歴は後続で実装予定")
        placeholder.setObjectName("mutedLabel")
        history_card.body.addWidget(placeholder)

        layout.addStretch()