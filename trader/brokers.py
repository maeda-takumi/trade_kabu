from __future__ import annotations

import json
from typing import Dict, Optional
from urllib import error as url_error
from urllib import request as url_request

from .enums import (
    FrontOrderType,
    ORDER_TYPE_TO_FRONT_ORDER_TYPE,
    OrderRole,
    OrderStatus,
)
from .models import Order, OrderPollResult


class BrokerInterface:
    """ブローカー（取引所APIなど）に依存する処理の抽象インターフェース。"""

    def place_order(self, order: Order) -> str:
        """注文送信。注文IDを返す。"""
        raise NotImplementedError

    def poll_order(self, order: Order) -> OrderPollResult:
        """注文状態のポーリング。"""
        raise NotImplementedError

    def cancel_order(self, order: Order) -> bool:
        """注文キャンセル。成功/失敗を返す。"""
        raise NotImplementedError


class DemoBroker(BrokerInterface):
    """デモ用の簡易ブローカー実装。指定回数のポーリング後に約定させる。"""

    def __init__(self, fills_after_polls: int = 2) -> None:
        self.fills_after_polls = fills_after_polls
        self._poll_counts: Dict[str, int] = {}
        self._next_id = 1

    def _required_polls(self, order: Order) -> int:
        if order.role == OrderRole.EXIT_PROFIT:
            return self.fills_after_polls + 1
        return self.fills_after_polls

    def place_order(self, order: Order) -> str:
        """注文IDを発行し、ポーリング回数を初期化する。"""
        order_id = f"DEMO-{self._next_id}"
        self._next_id += 1
        self._poll_counts[order_id] = 0
        return order_id

    def poll_order(self, order: Order) -> OrderPollResult:
        """指定回数まではSENT、それ以降はFILLEDを返す。"""
        if order.order_id is None:
            return OrderPollResult(status=OrderStatus.ERROR)
        self._poll_counts[order.order_id] += 1
        if self._poll_counts[order.order_id] > self._required_polls(order):
            return OrderPollResult(status=OrderStatus.FILLED, filled_qty=order.qty)
        return OrderPollResult(status=OrderStatus.SENT)

    def cancel_order(self, order: Order) -> bool:
        """常にキャンセル成功を返す簡易実装。"""
        return True


class KabuStationBroker(BrokerInterface):
    """kabuステーションAPI用ブローカー実装。"""

    def __init__(
        self,
        base_url: str,
        api_password: str,
        trading_password: Optional[str] = None,
        api_token: Optional[str] = None,
        timeout_sec: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_password = api_password
        self.trading_password = trading_password
        self.api_token = api_token
        self.timeout_sec = timeout_sec

    def fetch_token(self) -> str:
        """APIトークンを取得して保持する。

        仕様:
        - POST /kabusapi/token
        - Header: Content-Type: application/json
        - Body: {"APIPassword": "<APIパスワード>"}
        """
        response = self._request_json(
            "POST",
            "/kabusapi/token",
            {"APIPassword": self.api_password},
            require_token=False,
        )
        token = response.get("Token") or response.get("token")
        if not token:
            raise RuntimeError("トークン取得レスポンスに Token が含まれていません。")
        self.api_token = token
        return token

    def request_json(self, method: str, path: str, payload: Optional[dict] = None) -> dict:
        """APIリクエストを送り、トークン失効時は再取得して再試行する。"""
        if not self.api_token:
            self.fetch_token()
        try:
            return self._request_json(method, path, payload, require_token=True)
        except url_error.HTTPError as exc:
            if exc.code == 401:
                self.fetch_token()
                return self._request_json(method, path, payload, require_token=True)
            raise

    def place_order(self, order: Order) -> str:
        payload = self._build_order_payload(order)
        response = self.request_json("POST", "/kabusapi/sendorder", payload)
        result = response.get("Result")
        if result is not None and int(result) != 0:
            message = response.get("Msg") or response.get("Message") or "注文送信に失敗しました。"
            raise RuntimeError(f"kabuステーションAPI注文エラー(Result={result}): {message}")
        order_id = response.get("OrderId") or response.get("orderId")
        if not order_id:
            raise RuntimeError("注文レスポンスに OrderId が含まれていません。")
        return str(order_id)

    def poll_order(self, order: Order) -> OrderPollResult:
        if order.order_id is None:
            return OrderPollResult(status=OrderStatus.ERROR)
        response = self.request_json("GET", f"/kabusapi/orders?orderid={order.order_id}")
        result = response.get("Result") if isinstance(response, dict) else None
        if result is not None and int(result) != 0:
            message = response.get("Msg") or response.get("Message") or "注文照会に失敗しました。"
            order.last_error = f"kabuステーションAPI照会エラー(Result={result}): {message}"
            return OrderPollResult(status=OrderStatus.ERROR)
        order_payload = self._find_order_payload(order.order_id, response)
        status = self._map_order_status(order_payload)
        filled_qty = self._extract_filled_qty(order_payload)
        return OrderPollResult(status=status, filled_qty=filled_qty)

    def cancel_order(self, order: Order) -> bool:
        if order.order_id is None:
            return False
        payload = {
            "OrderId": order.order_id,
            "Password": self._require_trading_password(),
        }
        response = self.request_json("PUT", "/kabusapi/cancelorder", payload)
        result = response.get("Result", 1)
        if int(result) != 0:
            message = response.get("Msg") or response.get("Message") or "注文キャンセルに失敗しました。"
            order.last_error = f"kabuステーションAPIキャンセルエラー(Result={result}): {message}"
            return False
        return True

    def resolve_close_positions(self, symbol: str, side: int, qty: float) -> list[dict]:
        """信用返済用に建玉一覧からClosePositionsを組み立てる。"""
        response = self.request_json("GET", "/kabusapi/positions")
        positions = self._extract_positions(response)
        if symbol:
            positions = [pos for pos in positions if self._get_symbol(pos) == symbol]
        matched = [pos for pos in positions if self._get_side(pos) in (None, side)]
        if not matched:
            matched = positions
        remaining = qty
        close_positions: list[dict] = []
        for pos in matched:
            if remaining <= 0:
                break
            hold_id = self._get_hold_id(pos)
            position_qty = self._get_qty(pos)
            if not hold_id or position_qty <= 0:
                continue
            use_qty = min(position_qty, remaining)
            close_positions.append({"HoldID": hold_id, "Qty": use_qty})
            remaining -= use_qty
        if remaining > 0:
            raise RuntimeError("返済対象の建玉数量が不足しています。")
        return close_positions

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[dict],
        require_token: bool,
    ) -> dict:
        url = self._build_url(path)
        headers = {"Content-Type": "application/json"}
        if require_token and self.api_token:
            headers["X-API-KEY"] = self.api_token
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_obj = url_request.Request(url, data=data, headers=headers, method=method)
        try:
            with url_request.urlopen(request_obj, timeout=self.timeout_sec) as response:
                body = response.read().decode("utf-8")
        except url_error.HTTPError:
            raise
        except url_error.URLError as exc:
            raise RuntimeError("kabuステーションAPIへ接続できません。") from exc
        if not body:
            return {}
        return json.loads(body)

    def _build_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{path}"

    def _require_trading_password(self) -> str:
        if not self.trading_password:
            raise RuntimeError("取引パスワードが設定されていません。")
        return self.trading_password

    def _build_order_payload(self, order: Order) -> dict:
        password = self._require_trading_password()
        if order.front_order_type is None:
            mapped = ORDER_TYPE_TO_FRONT_ORDER_TYPE.get(order.order_type.upper())
            if mapped:
                order.front_order_type = mapped.value
        required_fields = {
            "Symbol": (order.symbol, "銘柄コード(Symbol)"),
            "Exchange": (order.exchange, "市場コード(Exchange)"),
            "Side": (order.side, "売買区分(Side: 1=買い, 2=売り)"),
            "CashMargin": (order.cash_margin, "現物/信用区分(CashMargin: 1=現物, 2=信用)"),
            "Qty": (order.qty, "数量(Qty)"),
            "FrontOrderType": (order.front_order_type, "執行条件(FrontOrderType)"),
        }
        missing = [label for _, (value, label) in required_fields.items() if value is None]
        if order.cash_margin == 2 and order.margin_trade_type is None:
            missing.append("信用区分(MarginTradeType: 1=信用新規, 2=信用返済)")
        if missing:
            details = " / ".join(missing)
            raise RuntimeError(
                f"注文送信に必要な項目が不足しています: {details}。"
                "UI入力とAPI仕様(/kabusapi/sendorder)の対応を確認してください。"
            )
        payload: dict[str, object] = {
            "Password": password,
            "Symbol": order.symbol,
            "Exchange": order.exchange,
            "Side": order.side,
            "CashMargin": order.cash_margin,
            "Qty": order.qty,
            "FrontOrderType": order.front_order_type,
        }
        optional_fields = {
            "SecurityType": order.security_type,
            "MarginTradeType": order.margin_trade_type,
            "AccountType": order.account_type,
            "DelivType": order.deliv_type,
            "ExpireDay": order.expire_day,
            "Price": order.price,
            "TimeInForce": order.time_in_force,
            "ClosePositionOrder": order.close_position_order,
            "FundType": order.fund_type,
        }
        for key, value in optional_fields.items():
            if value is not None:
                payload[key] = value
        if order.close_position_id:
            payload["ClosePositions"] = [{"HoldID": order.close_position_id, "Qty": order.qty}]
        if order.close_positions:
            close_positions: list[dict] = []
            for position in order.close_positions:
                hold_id = position.get("HoldID")
                qty_value = position.get("Qty")
                if not hold_id or qty_value is None:
                    raise RuntimeError("ClosePositionsのHoldIDとQtyが不足しています。")
                close_positions.append({"HoldID": hold_id, "Qty": qty_value})
            payload["ClosePositions"] = close_positions
        if order.stop_trigger_price is not None:
            if order.stop_under_over is None or order.stop_after_hit_order_type is None:
                raise RuntimeError("逆指値条件に必要な項目が不足しています。")
            reverse_limit = {
                "TriggerPrice": order.stop_trigger_price,
                "UnderOver": order.stop_under_over,
                "AfterHitOrderType": order.stop_after_hit_order_type,
            }
            if order.stop_after_hit_price is not None:
                reverse_limit["AfterHitPrice"] = order.stop_after_hit_price
            payload["ReverseLimitOrder"] = reverse_limit
        self._validate_order_payload(payload, order)
        return payload

    @staticmethod
    def _validate_order_payload(payload: dict, order: Order) -> None:
        front_order_type = payload.get("FrontOrderType")
        limit_types = {20, 21, 22, 24, 32}
        stop_types = {30, 31, 32}
        if front_order_type in limit_types and payload.get("Price") is None:
            raise RuntimeError("指値系の注文にはPriceが必須です。")
        if front_order_type in stop_types and "ReverseLimitOrder" not in payload:
            raise RuntimeError("逆指値注文にはReverseLimitOrderが必須です。")
        if front_order_type == 32:
            reverse_limit = payload.get("ReverseLimitOrder", {})
            if reverse_limit.get("AfterHitPrice") is None:
                raise RuntimeError("逆指値(指値)ではAfterHitPriceが必須です。")

    @staticmethod
    def _extract_positions(response: dict | list) -> list[dict]:
        if isinstance(response, list):
            return response
        if isinstance(response, dict):
            if "Details" in response and isinstance(response["Details"], list):
                return response["Details"]
            if "Positions" in response and isinstance(response["Positions"], list):
                return response["Positions"]
        return []

    @staticmethod
    def _get_hold_id(position: dict) -> Optional[str]:
        for key in ("HoldID", "HoldId", "hold_id", "ID", "Id"):
            if key in position and position[key]:
                return str(position[key])
        return None

    @staticmethod
    def _get_qty(position: dict) -> float:
        for key in ("Qty", "HoldQty", "LeavesQty", "PositionQty"):
            if key in position and position[key] is not None:
                try:
                    return float(position[key])
                except (TypeError, ValueError):
                    continue
        return 0.0

    @staticmethod
    def _get_symbol(position: dict) -> Optional[str]:
        for key in ("Symbol", "SymbolCode", "StockCode", "Code"):
            value = position.get(key)
            if value:
                return str(value)
        return None

    @staticmethod
    def _get_side(position: dict) -> Optional[int]:
        for key in ("Side", "BuySell", "SideCode"):
            value = position.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _find_order_payload(order_id: str, response: dict) -> dict:
        if not response:
            return {}
        if isinstance(response, list):
            for item in response:
                if str(item.get("OrderId")) == str(order_id):
                    return item
            return {}
        if isinstance(response, dict) and "Details" in response:
            for item in response.get("Details", []):
                if str(item.get("OrderId")) == str(order_id):
                    return item
        return response if isinstance(response, dict) else {}

    @staticmethod
    def _map_order_status(payload: dict) -> OrderStatus:
        state_value = payload.get("State") or payload.get("OrderState") or payload.get("Status")
        state_text = str(state_value or "").lower()
        if any(key in state_text for key in ("done", "filled", "約定", "complete")):
            return OrderStatus.FILLED
        if any(key in state_text for key in ("canceled", "cancel", "expired", "失効")):
            return OrderStatus.CANCELED
        if any(key in state_text for key in ("rejected", "reject", "却下")):
            return OrderStatus.REJECTED
        if any(key in state_text for key in ("partial", "一部")):
            return OrderStatus.PARTIAL
        if state_text.isdigit():
            state_code = int(state_text)
            status_map = {
                1: OrderStatus.SENT,
                2: OrderStatus.SENT,
                3: OrderStatus.PARTIAL,
                4: OrderStatus.FILLED,
                5: OrderStatus.CANCELED,
                6: OrderStatus.REJECTED,
                7: OrderStatus.CANCELED,
                8: OrderStatus.CANCELED,
            }
            mapped_status = status_map.get(state_code)
            if mapped_status:
                return mapped_status
        qty = payload.get("Qty") or payload.get("OrderQty")
        cum_qty = payload.get("CumQty") or payload.get("FilledQty") or payload.get("ExecuteQty")
        try:
            qty_value = float(qty) if qty is not None else None
            cum_value = float(cum_qty) if cum_qty is not None else None
        except (TypeError, ValueError):
            qty_value = None
            cum_value = None
        if qty_value and cum_value is not None:
            if cum_value >= qty_value:
                return OrderStatus.FILLED
            if 0 < cum_value < qty_value:
                return OrderStatus.PARTIAL
        if state_text:
            return OrderStatus.SENT
        return OrderStatus.ERROR

    @staticmethod
    def _extract_filled_qty(payload: dict) -> float:
        for key in ("CumQty", "FilledQty", "ExecuteQty", "Filled"):
            if key in payload and payload[key] is not None:
                try:
                    return float(payload[key])
                except (TypeError, ValueError):
                    continue
        return 0.0


__all__ = ["BrokerInterface", "DemoBroker", "KabuStationBroker"]