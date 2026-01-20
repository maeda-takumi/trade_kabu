from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


class Sidebar(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 24, 20, 24)
        layout.setSpacing(16)

        brand = QLabel("AutoTrader")
        brand.setObjectName("sidebarBrand")
        layout.addWidget(brand)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("sidebarList")
        self.list_widget.setSpacing(6)
        for label in ("設定画面", "注文画面", "注文履歴"):
            item = QListWidgetItem(label)
            item.setSizeHint(item.sizeHint())
            self.list_widget.addItem(item)
        self.list_widget.setCurrentRow(0)
        layout.addWidget(self.list_widget)

        layout.addStretch()

        meta = QLabel("v1.0 demo")
        meta.setObjectName("sidebarMeta")
        layout.addWidget(meta)