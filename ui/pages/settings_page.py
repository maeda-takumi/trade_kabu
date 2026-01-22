from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from autotrader import KabuStationBroker
from ui.widgets.card import Card


class SettingsPage(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(18)

        config_card = Card("AutoTrader設定")
        layout.addWidget(config_card)
        self._build_config(config_card.body)
        kabu_card = Card("kabuステーション設定")
        layout.addWidget(kabu_card)
        self._build_kabu_settings(kabu_card.body)
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
        layout.addWidget(group)

    def _build_kabu_settings(self, layout: QVBoxLayout) -> None:
        group = QGroupBox("KabuStation API")
        group.setCheckable(True)
        group.setChecked(True)
        group_layout = QFormLayout(group)
        group_layout.setHorizontalSpacing(16)
        group_layout.setVerticalSpacing(12)

        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("http://localhost:18080")
        self.base_url_input.setText("http://localhost:18080")
        group_layout.addRow("Base URL", self.base_url_input)

        self.api_password_input = QLineEdit()
        self.api_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        group_layout.addRow("APIパスワード", self.api_password_input)

        self.api_token_input = QLineEdit()
        group_layout.addRow("APIトークン", self.api_token_input)

        self.fetch_token_button = QPushButton("トークン取得")
        self.fetch_token_button.clicked.connect(self._handle_fetch_token)
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addWidget(self.fetch_token_button)
        button_layout.addStretch()
        group_layout.addRow("", button_container)

        layout.addWidget(group)

    def _handle_fetch_token(self) -> None:
        base_url = self.base_url_input.text().strip()
        api_password = self.api_password_input.text().strip()
        api_token = self.api_token_input.text().strip() or None
        if not base_url or not api_password:
            QMessageBox.warning(
                self,
                "入力不足",
                "Base URL と APIパスワードを入力してください。",
            )
            return
        broker = KabuStationBroker(
            base_url=base_url,
            api_password=api_password,
            api_token=api_token,
        )
        try:
            token = broker.fetch_token()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "トークン取得失敗",
                f"トークンの取得に失敗しました。\n{exc}",
            )
            return
        self.api_token_input.setText(token)
        QMessageBox.information(self, "トークン取得", "APIトークンを更新しました。")