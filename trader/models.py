from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Optional

from .enums import OrderRole, OrderStatus


@dataclass
class AutoTraderConfig:
    """強制決済などのタイムアウト系パラメータをまとめた設定。"""

    force_exit_poll_interval_sec: float = 3.0  # 強制決済中のポーリング間隔
    force_exit_max_duration_sec: float = 600.0  # 強制決済が失敗扱いになるまでの最大時間
    force_exit_start_before_close_min: int = 30  # 大引け前に強制決済を開始する目安
    force_exit_deadline_before_close_min: int = 10  # 大引け前の強制決済デッドライン
    market_close_hour: int = 15  # 大引け時刻(時)
    market_close_minute: int = 0  # 大引け時刻(分)
    force_exit_use_market_close: bool = True  # 閉場時刻で強制成行を動かすか
    reconcile_on_success: bool = True  # 約定成功時の再照合を実施するか


@dataclass(frozen=True)
class OrderPollResult:
    status: OrderStatus
    filled_qty: float = 0.0


@dataclass
class Order:
    """注文の内容を保持し、送信/状態確認/キャンセルを行う薄いラッパー。"""

    role: OrderRole
    order_type: str
    qty: float
    symbol: Optional[str] = None
    exchange: Optional[int] = None
    side: Optional[int] = None
    security_type: Optional[int] = None
    cash_margin: Optional[int] = None
    margin_trade_type: Optional[int] = None
    account_type: Optional[int] = None
    deliv_type: Optional[int] = None
    expire_day: Optional[int] = None
    front_order_type: Optional[int] = None
    symbol_code: Optional[str] = None
    time_in_force: Optional[str] = None
    price: Optional[float] = None
    close_position_id: Optional[str] = None
    close_position_order: Optional[int] = None
    close_positions: Optional[list[dict]] = None
    fund_type: Optional[str] = None
    stop_trigger_price: Optional[float] = None
    stop_after_hit_order_type: Optional[int] = None
    stop_after_hit_price: Optional[float] = None
    stop_under_over: Optional[int] = None
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.NEW
    filled_qty: float = 0.0
    last_error: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def place(self, broker: "BrokerInterface", repository: Optional["OrderRepository"] = None) -> None:
        """ブローカーに注文を送信し、注文IDを保存する。"""
        self.order_id = broker.place_order(self)
        self.status = OrderStatus.SENT
        if repository:
            repository.insert_order(self)

    def poll_status(
        self,
        broker: "BrokerInterface",
        repository: Optional["OrderRepository"] = None,
    ) -> OrderStatus:
        """ブローカーから最新状態を取得して保持する。"""
        previous_status = self.status
        previous_filled_qty = self.filled_qty
        poll_result = broker.poll_order(self)
        self.status = poll_result.status
        if poll_result.filled_qty:
            self.filled_qty = poll_result.filled_qty
        if self.status == OrderStatus.FILLED and not self.filled_qty:
            self.filled_qty = self.qty
        if repository and (self.status != previous_status or self.filled_qty != previous_filled_qty):
            repository.update_status(self)
        return self.status

    def cancel(self, broker: "BrokerInterface", repository: Optional["OrderRepository"] = None) -> bool:
        """ブローカーにキャンセルを依頼し、成功なら状態を更新する。"""
        success = broker.cancel_order(self)
        if success:
            self.status = OrderStatus.CANCELED
            if repository:
                repository.update_status(self)
        return success


@dataclass
class KabuStationConfig:
    base_url: str
    api_token: str
    trading_password: str
    timeout_sec: float = 10.0


__all__ = [
    "AutoTraderConfig",
    "KabuStationConfig",
    "Order",
    "OrderPollResult",
]