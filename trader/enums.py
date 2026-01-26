from __future__ import annotations

from enum import Enum, auto
from typing import Dict


class AutoTraderState(Enum):
    """状態機械の現在地を表すステータス。"""

    IDLE = auto()  # まだ注文を出していない待機状態
    ENTRY_WAIT = auto()  # 新規（エントリー）注文の約定待ち
    ENTRY_FILLED = auto()  # 新規注文が約定した直後
    EXIT_WAIT = auto()  # 利確/損切りの出口注文の約定待ち
    FORCE_EXITING = auto()  # 強制成行決済中
    EXIT_FILLED = auto()  # 決済完了
    ERROR = auto()  # 想定外の状態に入ったことを示す


class OrderRole(Enum):
    """注文の役割（どのフェーズの注文か）を表す分類。"""

    ENTRY = auto()  # 新規エントリー注文
    EXIT_PROFIT = auto()  # 利確注文
    EXIT_LOSS = auto()  # 損切り注文
    EXIT_MARKET = auto()  # 強制決済の成行注文


class OrderStatus(Enum):
    """ブローカーから返ってくる注文状態の簡易モデル。"""

    NEW = auto()  # まだブローカーに送っていない
    SENT = auto()  # 送信済み
    PARTIAL = auto()  # 一部約定
    FILLED = auto()  # 全部約定
    CANCELED = auto()  # キャンセル済み
    REJECTED = auto()  # 拒否
    ERROR = auto()  # エラー


class FrontOrderType(Enum):
    """kabuステーションAPIのFrontOrderTypeコード。"""

    MARKET = 10  # 成行
    MARKET_ON_OPEN = 11  # 寄成
    MARKET_ON_CLOSE = 12  # 引成
    MARKET_NO_EXECUTION = 13  # 不成
    IOC_MARKET = 14  # IOC成行
    LIMIT = 20  # 指値
    LIMIT_ON_OPEN = 21  # 寄指
    LIMIT_ON_CLOSE = 22  # 引指
    LIMIT_NO_EXECUTION = 23  # 不指
    IOC_LIMIT = 24  # IOC指値
    STOP = 30  # 逆指値
    STOP_MARKET = 31  # 逆指値(成行)
    STOP_LIMIT = 32  # 逆指値(指値)


class ReverseLimitUnderOver(Enum):
    """逆指値の判定方向。"""

    OVER = 1  # 指定価格以上で発動
    UNDER = 2  # 指定価格以下で発動


ORDER_TYPE_TO_FRONT_ORDER_TYPE: Dict[str, FrontOrderType] = {
    "MARKET": FrontOrderType.MARKET,
    "LIMIT": FrontOrderType.LIMIT,
    "STOP": FrontOrderType.STOP,
    "STOP_MARKET": FrontOrderType.STOP_MARKET,
    "STOP_LIMIT": FrontOrderType.STOP_LIMIT,
}