from __future__ import annotations

from datetime import datetime
import time
from typing import Optional

from PySide6.QtCore import QThread, Signal

from trader import (
    AutoTrader,
    AutoTraderConfig,
    AutoTraderState,
    KabuStationBroker,
    Order,
    OrderRole,
)
from ui.workers.demo_worker import TradeInputs


class LiveWorker(QThread):
    log_message = Signal(str)
    error_message = Signal(str)
    state_changed = Signal(str)
    exit_status_changed = Signal(str, str)
    finished_state = Signal(str)
    error_detail = Signal(str)

    def __init__(self, inputs: TradeInputs, parent: Optional[object] = None) -> None:
        super().__init__(parent=parent)
        self.inputs = inputs
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def _wait_until_scheduled(self) -> bool:
        if not self.inputs.scheduled_epoch:
            return True
        while True:
            if self._stop_requested:
                self.log_message.emit("[live] stop requested before scheduled start")
                return False
            now = time.time()
            if now >= self.inputs.scheduled_epoch:
                return True
            time.sleep(0.5)

    def run(self) -> None:
        phase = "初期化"
        try:
            config = AutoTraderConfig(
                force_exit_poll_interval_sec=self.inputs.force_exit_poll_interval_sec,
                force_exit_max_duration_sec=self.inputs.force_exit_max_duration_sec,
                force_exit_start_before_close_min=self.inputs.force_exit_start_before_close_min,
                force_exit_deadline_before_close_min=self.inputs.force_exit_deadline_before_close_min,
                force_exit_use_market_close=self.inputs.force_exit_use_market_close,
                market_close_hour=self.inputs.market_close_hour,
                market_close_minute=self.inputs.market_close_minute,
            )
            broker = KabuStationBroker(
                base_url=self.inputs.base_url,
                api_password=self.inputs.api_password,
                trading_password=self.inputs.trading_password,
                api_token=self.inputs.api_token,
            )
            if self.inputs.cash_margin == 2 and not self.inputs.close_positions:
                phase = "返済用建玉取得"
                self.inputs.close_positions = broker.resolve_close_positions(
                    self.inputs.symbol_code,
                    self.inputs.side_code,
                    self.inputs.qty,
                )
                self.log_message.emit(
                    "[live] ClosePositions auto-set from positions (credit)"
                )
            trader = AutoTrader(broker, config=config)
            phase = "エントリー注文準備"
            entry_price = (
                self.inputs.entry_price
                if self.inputs.entry_order_type == "LIMIT"
                else None
            )
            entry_order = Order(
                role=OrderRole.ENTRY,
                order_type=self.inputs.entry_order_type,
                qty=self.inputs.qty,
                symbol=self.inputs.symbol_code,
                exchange=self.inputs.exchange,
                symbol_code=self.inputs.symbol_code,
                side=self.inputs.side_code,
                cash_margin=self.inputs.cash_margin,
                security_type=self.inputs.security_type,
                account_type=self.inputs.account_type,
                deliv_type=self.inputs.deliv_type,
                expire_day=self.inputs.expire_day,
                close_position_order=self.inputs.close_position_order,
                price=entry_price,
                close_positions=self.inputs.close_positions,
                fund_type=self.inputs.fund_type,
            )

            self.log_message.emit(
                "[live] setup: "
                f"symbol={self.inputs.symbol_code}, exchange={self.inputs.exchange}, qty={self.inputs.qty}, "
                f"side={self.inputs.side_label}, order_type={self.inputs.entry_order_type}, "
                f"entry_price={self.inputs.entry_price}, profit={self.inputs.profit_price}, "
                f"loss={self.inputs.loss_price}"
            )

            if self.inputs.schedule_type == "予約" and self.inputs.scheduled_epoch:
                phase = "予約待機"
                scheduled_at = datetime.fromtimestamp(self.inputs.scheduled_epoch)
                self.log_message.emit(
                    f"[live] scheduled start at {scheduled_at:%Y-%m-%d %H:%M}"
                )
                if not self._wait_until_scheduled():
                    self.finished_state.emit("CANCELED")
                    return
            else:
                self.log_message.emit("[live] start immediately")

            phase = "エントリー注文送信"
            self.log_message.emit(f"[live] state={trader.state.name} -> start_trade")
            trader.start_trade(
                entry_order,
                profit_price=self.inputs.profit_price,
                loss_price=self.inputs.loss_price,
            )
            last_state = trader.state
            self.state_changed.emit(trader.state.name)
            self.log_message.emit(f"[live] state={trader.state.name}")
            self._emit_exit_statuses(trader, None)

            stopping = False
            last_exit_statuses: Optional[tuple[str, str]] = None
            while trader.state not in (
                AutoTraderState.EXIT_FILLED,
                AutoTraderState.ERROR,
            ):
                if self._stop_requested:
                    phase = "停止処理"
                    self.log_message.emit("[live] stop requested by user")
                    if trader.state in (
                        AutoTraderState.IDLE,
                        AutoTraderState.ENTRY_WAIT,
                    ):
                        trader.cancel_all_orders()
                        self.state_changed.emit(trader.state.name)
                        self.finished_state.emit("CANCELED")
                        return
                    if not stopping:
                        trader.force_exit_market()
                        stopping = True
                        if trader.state != last_state:
                            self.log_message.emit(
                                f"[live] state={last_state.name} -> {trader.state.name}"
                            )
                            last_state = trader.state
                            self.state_changed.emit(trader.state.name)
                phase = "注文ポーリング"
                trader.poll()
                if trader.state != last_state:
                    self.log_message.emit(
                        f"[live] state={last_state.name} -> {trader.state.name}"
                    )
                    last_state = trader.state
                    self.state_changed.emit(trader.state.name)
                current_exit_statuses = self._emit_exit_statuses(
                    trader, last_exit_statuses
                )
                if current_exit_statuses is not None:
                    last_exit_statuses = current_exit_statuses
                time.sleep(self.inputs.poll_interval_sec)

            phase = "完了処理"
            self.log_message.emit(f"[live] completed with state={trader.state.name}")
            self.state_changed.emit(trader.state.name)
            self._emit_exit_statuses(trader, last_exit_statuses)
            self.finished_state.emit(trader.state.name)
        except RuntimeError as exc:
            self._emit_error(phase, exc)
        except Exception as exc:
            self._emit_error(phase, exc)

    def _emit_exit_statuses(
        self, trader: AutoTrader, previous: Optional[tuple[str, str]]
    ) -> Optional[tuple[str, str]]:
        profit_status = (
            trader.exit_profit_order.status.name
            if trader.exit_profit_order
            else "NOT_SENT"
        )
        loss_status = (
            trader.exit_loss_order.status.name if trader.exit_loss_order else "NOT_SENT"
        )
        current = (profit_status, loss_status)
        if current != previous:
            self.exit_status_changed.emit(*current)
        return current

    def _emit_error(self, phase: str, exc: Exception) -> None:
        exc_type = type(exc).__name__
        exc_message = str(exc).strip() or "(メッセージなし)"
        detail = (
            "モード: 実運用\n"
            f"フェーズ: {phase}\n"
            f"例外: {exc_type}\n"
            f"メッセージ: {exc_message}"
        )
        self.log_message.emit(
            f"[live][error] {phase}で例外発生 ({exc_type}): {exc_message}"
        )
        self.error_detail.emit(detail)
        self.finished_state.emit("ERROR")