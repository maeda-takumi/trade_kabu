# 自動売買クラス設計書（AutoTrader）

## 1. 目的
本設計書は、kabuステーションAPIを利用した自動売買システムにおける  
「自動売買クラス（AutoTrader）」および関連クラスの責務・構造・状態遷移を定義する。

kabuステーションAPIはデモ環境を持たず、OCO注文等の高度注文も未提供のため、  
自動売買ロジックおよび注文制御はアプリケーション側で実装する。

---

## 2. 前提条件・制約（kabuステAPI特性）

- APIは単発注文のみ（OCO / IFD / IFDOCO 非対応）
- 注文成功 ≠ 約定
- 注文状態はポーリングで取得する必要がある
- 部分約定・未約定・失効が発生する
- WebSocketによる即時通知は想定しない
- APIエラーは業務エラーとして扱う必要がある
- 本番環境のみのため、Demoモード実装が必須

---

## 3. システム全体構成

```
UI / Controller
   ↓
AutoTrader（管理クラス）
   ↓
Order（注文クラス：複数インスタンス）
   ↓
BrokerInterface
   ├─ KabuStationBroker（本番）
   └─ DemoBroker（デモ）
```

---

## 4. 設計方針（重要）

- 注文クラスは1種類のみとする
- 注文の違いは「役割（role）」によって表現する
- 判断ロジックはすべて AutoTrader に集約する
- Order は自律的に約定状況を確認し、結果のみを報告する
- AutoTrader は Order からの報告を元に他 Order を制御する
- Demo / Live の違いは Broker で吸収する

---

## 5. AutoTrader の責務

AutoTrader は「1トレード（1エントリー〜1エグジット）」を管理する。

### 主な責務
- トレード全体の状態管理
- Order インスタンスの生成・管理
- Order からのイベント受信と判断
- 擬似OCO（利確・損切）制御
- 異常時の安全終了制御

---

## 6. AutoTrader の状態定義

```
IDLE
ENTRY_WAIT
ENTRY_FILLED
EXIT_WAIT
EXIT_FILLED
ERROR
```

---

## 7. Order クラス仕様

### 7.1 役割
Order は単一の注文を表すクラスであり、以下の責務を持つ。

- 注文の発注
- 注文状態の保持
- 約定状況の定期確認（polling）
- 状態変化の AutoTrader への報告

※ Order は判断ロジックを一切持たない

---

### 7.2 Order の役割種別（role）

```
ENTRY        エントリー注文
EXIT_PROFIT  利確注文
EXIT_LOSS    損切注文
EXIT_MARKET  成行決済注文（緊急用）
```

---

### 7.3 Order の状態定義

```
NEW
SENT
PARTIAL
FILLED
CANCELED
REJECTED
ERROR
```

---

### 7.4 Order が保持する属性（例）

- role
- order_type（LIMIT / MARKET）
- price（指値時のみ）
- qty
- order_id
- status
- created_at

---

### 7.5 Order のメソッド

- place()  
  注文を発注する

- poll_status()  
  注文状態を確認する

- cancel()  
  注文をキャンセルする

- report_event()  
  状態変化を AutoTrader に通知する

---

## 8. AutoTrader クラス仕様

### 8.1 AutoTrader が保持する属性

- state
- broker
- orders（管理中の Order インスタンス）
- entry_order
- exit_profit_order
- exit_loss_order

---

### 8.2 AutoTrader の主要メソッド

- start_trade()  
  トレードを開始する

- on_order_event(order, event)  
  Order からの報告を受け取る

- create_exit_orders()  
  利確・損切注文を生成する

- cancel_other_exit_orders(filled_order)  
  擬似OCO制御

- force_exit_market()  
  緊急時の成行決済

- cancel_all_orders()  
  全注文キャンセル

---

## 9. Order ⇄ AutoTrader の責務境界

| 項目 | Order | AutoTrader |
|---|---|---|
| 注文発注 | ○ | × |
| 約定確認 | ○ | × |
| 状態判断 | × | ○ |
| 他注文制御 | × | ○ |
| OCO制御 | × | ○ |

---

## 10. 擬似OCO制御フロー

1. ENTRY 注文が約定
2. EXIT_PROFIT / EXIT_LOSS 注文を同時発注
3. どちらかが約定
4. 残りの注文を即時キャンセル
5. トレード終了

---

## 11. Demoモード設計方針

- BrokerInterface による API 抽象化
- DemoBroker にて以下を擬似再現
  - 約定遅延
  - 未約定
  - 部分約定
  - APIエラー
- AutoTrader / Order は Demo / Live を意識しない

---

## 12. 異常系・安全設計

- 状態不整合時は ERROR 遷移
- EXIT注文が両方約定した場合は即 ERROR
- キャンセル失敗時は成行決済を優先

---

## 13. 将来拡張（スコープ外）

- 複数トレード管理
- 複数銘柄対応
- ロット分割
- トレーリングストップ
- 永続化（DB / ファイル）
