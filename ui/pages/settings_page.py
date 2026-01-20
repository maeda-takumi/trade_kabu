from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QFormLayout, QGroupBox, QSpinBox, QDoubleSpinBox, QVBoxLayout, QWidget

from ui.widgets.card import Card


class SettingsPage(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(18)

        config_card = Card("AutoTrader設定")
        layout.addWidget(config_card)
        self._build_config(config_card.body)
        layout.addStretch()

    def _build_config(self, layout: QVBoxLayout) -> None:
        group = QGroupBox("AutoTraderConfig")
        group.setCheckable(True)
        group.setChecked(True)
        group_layout = QFormLayout(group)
        group_layout.setHorizontalSpacing(16)
        group_layout.setVerticalSpacing(12)

        self.force_poll_interval_input = QDoubleSpinBox()
        self.force_poll_interval_input.setRange(0.5, 10.0)
        self.force_poll_interval_input.setSingleStep(0.5)
        self.force_poll_interval_input.setValue(3.0)
        group_layout.addRow("強制決済ポーリング(秒)", self.force_poll_interval_input)

        self.force_max_duration_input = QDoubleSpinBox()
        self.force_max_duration_input.setRange(60.0, 3600.0)
        self.force_max_duration_input.setSingleStep(60.0)
        self.force_max_duration_input.setValue(600.0)
        group_layout.addRow("強制決済最大時間(秒)", self.force_max_duration_input)

        self.force_start_before_input = QSpinBox()
        self.force_start_before_input.setRange(1, 60)
        self.force_start_before_input.setValue(30)
        group_layout.addRow("強制決済開始目安(分)", self.force_start_before_input)

        self.force_deadline_before_input = QSpinBox()
        self.force_deadline_before_input.setRange(1, 60)
        self.force_deadline_before_input.setValue(10)
        group_layout.addRow("強制決済デッドライン(分)", self.force_deadline_before_input)

        layout.addWidget(group)