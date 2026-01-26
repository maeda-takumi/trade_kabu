from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import time
from typing import Dict, Optional

from .brokers import BrokerInterface, DemoBroker
from .enums import (
    AutoTraderState,
    FrontOrderType,
    ORDER_TYPE_TO_FRONT_ORDER_TYPE,
    OrderRole,
    OrderStatus,
    ReverseLimitUnderOver,
)
from .models import AutoTraderConfig, Order
from .repository import OrderRepository


class AutoTrader:
    """エントリーから決済までを管理する状態機械。"""

    def __init__(
        self,
        broker: BrokerInterface,
        config: Optional[AutoTraderConfig] = None,
        repository: Optional[OrderRepository] = None,
    ) -> None:
        self.broker = broker
        self.config = config or AutoTraderConfig()
        default_db_path = Path(__file__).resolve().parents[1] / "trade.db"
        self.repository = repository or OrderRepository(default_db_path)
        self.state = AutoTraderState.IDLE
        # 役割別の注文をまとめて管理する辞書（同じ役割の注文は最新が入る）
        self.orders: Dict[OrderRole, Order] = {}
        self.entry_order: Optional[Order] = None
        self.exit_profit_order: Optional[Order] = None
        self.exit_loss_order: Optional[Order] = None
        self._profit_price: Optional[float] = None
        self._loss_price: Optional[float] = None
        self._force_exit_started_at: Optional[float] = None
        self._last_force_exit_poll: Optional[float] = None
        self._confirmed_order_ids: set[str] = set()

    def _enter_error_state(self) -> None:
        """エラー状態へ遷移し、未約定注文を可能な限り取り消す。"""
        self.state = AutoTraderState.ERROR
        self.cancel_all_orders()

    @staticmethod
    def calculate_qty(capital: float, entry_price: float) -> int:
        """軍資金とエントリー価格から注文数量を算出する（端数切り捨て）。"""
        if entry_price <= 0:
            return 0
        return int(capital // entry_price)

    def start_trade(self, entry_order: Order, profit_price: float, loss_price: float) -> None:
        """取引を開始する。IDLEでない場合はERRORに遷移する。"""
        if self.state != AutoTraderState.IDLE:
            self.state = AutoTraderState.ERROR
            return
        self._profit_price = profit_price
        self._loss_price = loss_price
        # 新規エントリー注文を送信
        if entry_order.cash_margin == 2 and entry_order.margin_trade_type is None:
            entry_order.margin_trade_type = 1
        if entry_order.front_order_type is None:
            mapped = ORDER_TYPE_TO_FRONT_ORDER_TYPE.get(entry_order.order_type.upper())
            if mapped:
                entry_order.front_order_type = mapped.value
        self.entry_order = entry_order
        self.orders[entry_order.role] = entry_order
        entry_order.place(self.broker, repository=self.repository)
        self.state = AutoTraderState.ENTRY_WAIT

    def on_order_event(self, order: Order, status: OrderStatus) -> None:
        """注文ステータス変化に応じて状態遷移と後続処理を行う。"""
        if self.state == AutoTraderState.ERROR:
            return
        if status in (OrderStatus.REJECTED, OrderStatus.ERROR):
            self._enter_error_state()
            return
        # エントリーが約定したら利確/損切り注文を作る
        if order.role == OrderRole.ENTRY and status == OrderStatus.FILLED:
            self.state = AutoTraderState.ENTRY_FILLED
            self.create_exit_orders()
        # 利確 or 損切りのいずれかが約定したら他方をキャンセル
        elif order.role in (OrderRole.EXIT_PROFIT, OrderRole.EXIT_LOSS) and status == OrderStatus.FILLED:
            other_role = (
                OrderRole.EXIT_LOSS if order.role == OrderRole.EXIT_PROFIT else OrderRole.EXIT_PROFIT
            )
            other_order = self.orders.get(other_role)
            if other_order and other_order.status == OrderStatus.FILLED:
                self._enter_error_state()
                return

            self.cancel_other_exit_orders(order)
            if self.state != AutoTraderState.ERROR:
                self.state = AutoTraderState.EXIT_FILLED
        # 成行強制決済が約定したら終了
        elif order.role == OrderRole.EXIT_MARKET and status == OrderStatus.FILLED:
            self.state = AutoTraderState.EXIT_FILLED

    def _confirm_order_filled(self, order: Order) -> bool:
        if not self.config.reconcile_on_success:
            return True
        if order.order_id is None or order.order_id in self._confirmed_order_ids:
            return True
        confirmed_status = order.poll_status(self.broker, repository=self.repository)
        if confirmed_status == OrderStatus.FILLED:
            self._confirmed_order_ids.add(order.order_id)
            return True
        return False

    def create_exit_orders(self) -> None:
        """利確/損切り注文を作成して送信する。"""
        if not self.entry_order:
            self.state = AutoTraderState.ERROR
            return
        if self._profit_price is None or self._loss_price is None:
            # 利確/損切価格が未設定ならエラーにする
            self.state = AutoTraderState.ERROR
            return
        exit_side = self._resolve_exit_side()
        if exit_side is None and not isinstance(self.broker, DemoBroker):
            self.state = AutoTraderState.ERROR
            return
        base_kwargs = self._build_exit_order_base(exit_side)
        if self.entry_order.cash_margin == 2:
            base_kwargs["margin_trade_type"] = 2
        stop_under_over = self._resolve_stop_under_over()
        if stop_under_over is None and not isinstance(self.broker, DemoBroker):
            self.state = AutoTraderState.ERROR
            return
        # エントリー数量に合わせて両建ての出口注文を作る
        self.exit_profit_order = Order(
            role=OrderRole.EXIT_PROFIT,
            order_type="LIMIT",
            qty=self.entry_order.qty,
            front_order_type=FrontOrderType.LIMIT.value,
            price=self._profit_price,
            **base_kwargs,
        )

        self.exit_loss_order = Order(
            role=OrderRole.EXIT_LOSS,
            order_type="STOP",
            qty=self.entry_order.qty,
            front_order_type=FrontOrderType.STOP.value,
            stop_trigger_price=self._loss_price,
            stop_under_over=stop_under_over,
            stop_after_hit_order_type=FrontOrderType.MARKET.value,
            **base_kwargs,
        )
        print(
            "[demo] create exit orders: "
            f"profit={self.exit_profit_order.order_type} price={self.exit_profit_order.price} qty={self.exit_profit_order.qty}, "
            f"loss={self.exit_loss_order.order_type} price={self.exit_loss_order.price} qty={self.exit_loss_order.qty}"
        )
        self.orders[self.exit_profit_order.role] = self.exit_profit_order
        self.orders[self.exit_loss_order.role] = self.exit_loss_order

        # OCOがない前提のため、損切→利確の順に送信する
        self.exit_loss_order.place(self.broker, repository=self.repository)
        self.exit_profit_order.place(self.broker, repository=self.repository)
        self.state = AutoTraderState.EXIT_WAIT

    def cancel_other_exit_orders(self, filled_order: Order) -> None:
        """片方が約定したらもう片方をキャンセルする。"""
        for role in (OrderRole.EXIT_PROFIT, OrderRole.EXIT_LOSS):
            order = self.orders.get(role)
            if order and order is not filled_order:
                success = order.cancel(self.broker, repository=self.repository)
                if not success:
                    self.force_exit_market()
                    if self.state != AutoTraderState.FORCE_EXITING:
                        self._enter_error_state()

    def force_exit_market(self) -> None:
        """強制決済（成行）を実行する。"""
        if self.state in (AutoTraderState.IDLE, AutoTraderState.ENTRY_WAIT):
            # まだポジションがない段階での強制決済はエラー扱い
            self.state = AutoTraderState.ERROR
            return
        if self.state in (AutoTraderState.EXIT_FILLED, AutoTraderState.ERROR):
            # すでに終わっているかエラーなら何もしない
            return
        exit_side = self._resolve_exit_side()
        if exit_side is None and not isinstance(self.broker, DemoBroker):
            self.state = AutoTraderState.ERROR
            return
        base_kwargs = self._build_exit_order_base(exit_side)
        exit_order = Order(
            role=OrderRole.EXIT_MARKET,
            order_type="MARKET",
            qty=self.entry_order.qty if self.entry_order else 0,
            close_position_id=self.entry_order.close_position_id if self.entry_order else None,
            close_positions=self.entry_order.close_positions if self.entry_order else None,
            front_order_type=FrontOrderType.MARKET.value,
            **base_kwargs,
        )
        self.orders[exit_order.role] = exit_order
        exit_order.place(self.broker, repository=self.repository)
        self.state = AutoTraderState.FORCE_EXITING
        # 強制決済用のタイムスタンプを記録
        now = time.monotonic()
        self._force_exit_started_at = now
        self._last_force_exit_poll = now

    def cancel_all_orders(self) -> None:
        """未約定の注文をすべてキャンセルする。"""
        for order in list(self.orders.values()):
            if order.status not in (OrderStatus.FILLED, OrderStatus.CANCELED):
                order.cancel(self.broker, repository=self.repository)

    def poll(self) -> None:
        """状態に応じて注文のポーリング処理を実行する。"""
        self._maybe_force_exit_by_market_close()
        if self.state in (
            AutoTraderState.ENTRY_WAIT,
            AutoTraderState.EXIT_WAIT,
            AutoTraderState.FORCE_EXITING,
        ):
            self._poll_active_orders()

    def _maybe_force_exit_by_market_close(self) -> None:
        if not self.config.force_exit_use_market_close:
            return
        if self.state in (AutoTraderState.EXIT_FILLED, AutoTraderState.ERROR):
            return
        now = datetime.now()
        close_time = now.replace(
            hour=self.config.market_close_hour,
            minute=self.config.market_close_minute,
            second=0,
            microsecond=0,
        )
        start_time = close_time - timedelta(minutes=self.config.force_exit_start_before_close_min)
        deadline_time = close_time - timedelta(minutes=self.config.force_exit_deadline_before_close_min)
        if now < start_time:
            return
        if self.state != AutoTraderState.FORCE_EXITING:
            if now <= deadline_time:
                self.force_exit_market()
            else:
                self._enter_error_state()

    def _poll_active_orders(self) -> None:
        """アクティブな注文をポーリングし、状態遷移を処理する。"""
        now = time.monotonic()
        if self.state == AutoTraderState.FORCE_EXITING:
            # 強制決済が長引きすぎたらエラーにする
            if self._force_exit_started_at and now - self._force_exit_started_at > self.config.force_exit_max_duration_sec:
                self.state = AutoTraderState.ERROR
                return
            # 強制決済中は一定間隔でのみポーリング
            if self._last_force_exit_poll and now - self._last_force_exit_poll < self.config.force_exit_poll_interval_sec:
                return
            self._last_force_exit_poll = now
        for order in list(self.orders.values()):
            # すでに確定した注文はスキップ
            if order.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.ERROR):
                continue
            status = order.poll_status(self.broker, repository=self.repository)
            if status in (OrderStatus.REJECTED, OrderStatus.ERROR):
                self._enter_error_state()
                return
            # 強制決済時に一部約定なら成行を出し直す
            if status == OrderStatus.PARTIAL:
                if self._handle_partial_fill(order):
                    continue
            # 状態変化に応じた処理へ
            self.on_order_event(order, status)

    def _handle_partial_fill(self, order: Order) -> bool:
        """部分約定時に残量分の注文を再送する。処理した場合はTrue。"""
        if order.filled_qty <= 0 or order.filled_qty >= order.qty:
            return False
        remaining_qty = order.qty - order.filled_qty
        if remaining_qty <= 0:
            return False
        if self.state == AutoTraderState.FORCE_EXITING:
            replacement = Order(
                role=OrderRole.EXIT_MARKET,
                order_type="MARKET",
                qty=remaining_qty,
                symbol=order.symbol,
                exchange=order.exchange,
                side=order.side,
                security_type=order.security_type,
                cash_margin=order.cash_margin,
                margin_trade_type=order.margin_trade_type,
                account_type=order.account_type,
                deliv_type=order.deliv_type,
                expire_day=order.expire_day,
                front_order_type=order.front_order_type,
                symbol_code=order.symbol_code,
                time_in_force=order.time_in_force,
                price=order.price,
                stop_trigger_price=order.stop_trigger_price,
                stop_after_hit_order_type=order.stop_after_hit_order_type,
                stop_after_hit_price=order.stop_after_hit_price,
                stop_under_over=order.stop_under_over,
                close_positions=order.close_positions,
                close_position_order=order.close_position_order,
                fund_type=order.fund_type,
            )
            self.orders[replacement.role] = replacement
            replacement.place(self.broker, repository=self.repository)
            return True
        if not order.cancel(self.broker, repository=self.repository):
            self._enter_error_state()
            return True
        replacement = Order(
            role=order.role,
            order_type=order.order_type,
            qty=remaining_qty,
            price=order.price,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            security_type=order.security_type,
            cash_margin=order.cash_margin,
            margin_trade_type=order.margin_trade_type,
            account_type=order.account_type,
            deliv_type=order.deliv_type,
            expire_day=order.expire_day,
            front_order_type=order.front_order_type,
            symbol_code=order.symbol_code,
            time_in_force=order.time_in_force,
            stop_trigger_price=order.stop_trigger_price,
            stop_after_hit_order_type=order.stop_after_hit_order_type,
            stop_after_hit_price=order.stop_after_hit_price,
            stop_under_over=order.stop_under_over,
            close_positions=order.close_positions,
            close_position_order=order.close_position_order,
            fund_type=order.fund_type,
        )
        self.orders[replacement.role] = replacement
        replacement.place(self.broker, repository=self.repository)
        return True

    def _resolve_exit_side(self) -> Optional[int]:
        if not self.entry_order:
            return None
        if self.entry_order.side is None:
            return None
        # TODO: kabuステーションAPIのSide仕様に合わせて明示的に変換する。
        if self.entry_order.side == 1:
            return 2
        if self.entry_order.side == 2:
            return 1
        return None

    def _resolve_stop_under_over(self) -> Optional[int]:
        if not self.entry_order:
            return None
        if self.entry_order.side == 1:
            return ReverseLimitUnderOver.UNDER.value
        if self.entry_order.side == 2:
            return ReverseLimitUnderOver.OVER.value
        return None

    def _build_exit_order_base(self, exit_side: Optional[int]) -> dict:
        if not self.entry_order:
            return {}
        return {
            "symbol": self.entry_order.symbol,
            "exchange": self.entry_order.exchange,
            "side": exit_side,
            "security_type": self.entry_order.security_type,
            "cash_margin": self.entry_order.cash_margin,
            "margin_trade_type": self.entry_order.margin_trade_type,
            "account_type": self.entry_order.account_type,
            "deliv_type": self.entry_order.deliv_type,
            "expire_day": self.entry_order.expire_day,
            "symbol_code": self.entry_order.symbol_code,
            "time_in_force": self.entry_order.time_in_force,
            "close_position_id": self.entry_order.close_position_id,
            "close_positions": self.entry_order.close_positions,
            "close_position_order": self.entry_order.close_position_order,
            "fund_type": self.entry_order.fund_type,
        }



def run_demo(
    poll_interval_sec: float = 0.5,
    fills_after_polls: int = 2,
    profit_price: float = 105.0,
    loss_price: float = 95.0,
) -> AutoTraderState:
    broker = DemoBroker(fills_after_polls=fills_after_polls)
    trader = AutoTrader(broker)
    entry_order = Order(role=OrderRole.ENTRY, order_type="MARKET", qty=1)
    print(f"[demo] state={trader.state.name} -> start_trade")
    trader.start_trade(entry_order, profit_price=profit_price, loss_price=loss_price)
    last_state = trader.state
    print(f"[demo] state={last_state.name}")
    while trader.state not in (AutoTraderState.EXIT_FILLED, AutoTraderState.ERROR):
        trader.poll()
        if trader.state != last_state:
            print(f"[demo] state={last_state.name} -> {trader.state.name}")
            last_state = trader.state
        time.sleep(poll_interval_sec)
    print(f"[demo] completed with state={trader.state.name}")
    return trader.state


__all__ = ["AutoTrader", "run_demo"]