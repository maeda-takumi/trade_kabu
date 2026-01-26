# kabuステーションAPI まとめ（REST/PUSH）

> 公式リファレンスから要点を抜き出して「使うために必要な情報」を1つにまとめたメモです。  
> 更新日: 2026-01-26（JST）

---

## 公式URL（参照元）

- REST API リファレンス  
  https://kabucom.github.io/kabusapi/reference/index.html
- 開発者ポータル（入口）  
  https://kabucom.github.io/kabusapi/ptal/
- OpenAPI（YAML）  
  https://raw.githubusercontent.com/kabucom/kabusapi/master/reference/kabu_STATION_API.yaml
- PUSH API（WebSocket）説明  
  https://kabucom.github.io/kabusapi/ptal/push.html

---

## 1. 全体像（どういうAPI？）

- **kabuステーション（Windowsアプリ）がローカルでAPIサーバとして動く**タイプ  
- HTTPで叩く **REST API** と、WebSocketでリアルタイム受信する **PUSH API** の2系統
- 本番/検証でポートが分かれている（下記）

---

## 2. 接続先（ベースURL）

### REST API
- 本番: `http://localhost:18080/kabusapi`
- 検証: `http://localhost:18081/kabusapi`

### PUSH API（WebSocket）
- 本番: `ws://localhost:18080/kabusapi/websocket`
- 検証: `ws://localhost:18081/kabusapi/websocket`

---

## 3. 認証（トークン方式）

### 手順
1) `POST /token` に `APIPassword` を渡して **APIトークン** を発行  
2) 以降のRESTリクエストは **Header `X-API-KEY` にトークン** を付けて実行

### トークンが無効になる条件（重要）
- kabuステーションを終了した時  
- kabuステーションからログアウトした時  
- 別のトークンを新たに発行した時  
- **早朝に強制ログアウトされる**ことがある（運用上の注意）

---

## 4. 流量制限（ざっくり）

OpenAPIのタグ説明より：

- **発注系**: 秒間5件程度
- **取引余力系**: 秒間10件程度
- **情報系（板/銘柄/残高/注文照会など）**: 秒間10件程度

---

## 5. 銘柄登録の上限

- REST/PUSH 合算で **最大50銘柄**まで登録可能  
  （「登録」系エンドポイントで管理し、PUSH配信対象にもなる）

---

## 6. 主要エンドポイント一覧（REST）

### 認証（auth）
| Method | Path | Summary |
| --- | --- | --- |
| `POST` | `/token` | トークン発行 |

### 発注（order）
| Method | Path | Summary |
| --- | --- | --- |
| `PUT` | `/cancelorder` | 注文取消 |
| `POST` | `/sendorder` | 注文発注（現物・信用） |
| `POST` | `/sendorder/future` | 注文発注（先物） |
| `POST` | `/sendorder/option` | 注文発注（オプション） |

### 取引余力（wallet）
| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/wallet/cash` | 取引余力（現物） |
| `GET` | `/wallet/cash/{symbol}` | 取引余力（現物）（銘柄指定） |
| `GET` | `/wallet/future` | 取引余力（先物） |
| `GET` | `/wallet/future/{symbol}` | 取引余力（先物）（銘柄指定） |
| `GET` | `/wallet/margin` | 取引余力（信用） |
| `GET` | `/wallet/margin/{symbol}` | 取引余力（信用）（銘柄指定） |
| `GET` | `/wallet/option` | 取引余力（オプション） |
| `GET` | `/wallet/option/{symbol}` | 取引余力（オプション）（銘柄指定） |

### 情報（info）
| Method | Path | Summary |
| --- | --- | --- |
| `GET` | `/apisoftlimit` | ソフトリミット |
| `GET` | `/board/{symbol}` | 時価情報・板情報 |
| `GET` | `/exchange/{symbol}` | 為替情報 |
| `GET` | `/margin/marginpremium/{symbol}` | プレミアム料取得 |
| `GET` | `/orders` | 注文約定照会 |
| `GET` | `/positions` | 残高照会 |
| `GET` | `/primaryexchange/{symbol}` | 優先市場 |
| `GET` | `/ranking` | 詳細ランキング |
| `GET` | `/regulations/{symbol}` | 規制情報 |
| `GET` | `/symbol/{symbol}` | 銘柄情報 |
| `GET` | `/symbolname/future` | 先物銘柄コード取得 |
| `GET` | `/symbolname/minioptionweekly` | ミニオプション（限週）銘柄コード取得 |
| `GET` | `/symbolname/option` | オプション銘柄コード取得 |

### 銘柄登録（register）
| Method | Path | Summary |
| --- | --- | --- |
| `PUT` | `/register` | 銘柄登録 |
| `PUT` | `/unregister` | 銘柄登録解除 |
| `PUT` | `/unregister/all` | 銘柄登録全解除 |

---

## 7. 最低限覚えておくリクエスト/レスポンス（抜粋）

### 7.1 トークン発行

#### Request: `POST /token`
| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `APIPassword` | `string` | 必須 | APIパスワード |

#### Response: `200 OK`
| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `ResultCode` | `integer` | 任意 | 結果コード 0が成功。それ以外はエラーコード。 |
| `Token` | `string` | 任意 | APIトークン |

---

### 7.2 注文発注（現物・信用）

#### Request: `POST /sendorder`
（項目が多いので「よく使うもの中心」で理解するのがおすすめ）

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `Symbol` | `string` | 必須 | 銘柄コード |
| `Exchange` | `integer` | 必須 | 市場コード <thead> <tr> <th>定義値</th> <th>説明</th> </tr> </thead> <tbody> <tr> 1 東証 ... |
| `SecurityType` | `integer` | 必須 | 商品種別 <thead> <tr> <th>定義値</th> <th>説明</th> </tr> </thead> <tbody> <tr> 1 株式 <... |
| `Side` | `string` | 必須 | 売買区分 <thead> <tr> <th>定義値</th> <th>説明</th> </tr> </thead> <tbody> <tr> 1 売 </... |
| `CashMargin` | `integer` | 必須 | 信用区分 <thead> <tr> <th>定義値</th> <th>説明</th> </tr> </thead> <tbody> <tr> 1 現物 <... |
| `MarginTradeType` | `integer` | 任意 | 信用取引区分 ※現物取引の場合は指定不要。 ※信用取引の場合、必須。 <thead> <tr> <th>定義値</th> <th>説明</th> </tr... |
| `MarginPremiumUnit` | `number` | 任意 | １株あたりのプレミアム料(円) ※プレミアム料の刻値は、プレミアム料取得APIのレスポンスにある"TickMarginPremium"にてご確認ください。... |
| `DelivType` | `integer` | 必須 | 受渡区分 ※現物買は指定必須。 ※現物売は「0(指定なし)」を設定 ※信用新規は「0(指定なし)」を設定 ※信用返済は指定必須 ※auマネーコネクトが有効... |
| `FundType` | `string` | 任意 | 資産区分（預り区分） ※現物買は、指定必須。 ※現物売は、「' '」 半角スペース2つを指定必須。 ※信用新規と信用返済は、「11」を指定するか、または指... |
| `AccountType` | `integer` | 必須 | 口座種別 <thead> <tr> <th>定義値</th> <th>説明</th> </tr> </thead> <tbody> <tr> 2 一般 <... |
| `Qty` | `integer` | 必須 | 注文数量 ※信用一括返済の場合、返済したい合計数量を入力してください。 |
| `ClosePositionOrder` | `integer` | 任意 | 決済順序 ※信用返済の場合、必須。 ※ClosePositionOrderとClosePositionsはどちらか一方のみ指定可能。 ※ClosePosi... |
| `ClosePositions` | `array` | 任意 | 返済建玉指定 ※信用返済の場合、必須。 ※ClosePositionOrderとClosePositionsはどちらか一方のみ指定可能。 ※ClosePo... |
| `FrontOrderType` | `integer` | 必須 | 執行条件 ※SOR以外は以下、全て指定可能です。 <thead> <tr> <th>定義値</th> <th>説明</th> <th>”Price"の指定... |
| `Price` | `number` | 必須 | 注文価格 ※FrontOrderTypeで成行を指定した場合、0を指定する。 ※詳細について、”FrontOrderType”をご確認ください。 |
| `ExpireDay` | `integer` | 必須 | 注文有効期限 yyyyMMdd形式。 「0」を指定すると、kabuステーション上の発注画面の「本日」に対応する日付として扱います。 「本日」は直近の注文可... |
| `ReverseLimitOrder` | `object` | 任意 | 逆指値条件 ※FrontOrderTypeで逆指値を指定した場合のみ必須。 |

#### Response: `200 OK`
| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `Result` | `integer` | 任意 | 結果コード 0が成功。それ以外はエラーコード。 |
| `OrderId` | `string` | 任意 | 受付注文番号 |

---

### 7.3 注文取消

#### Request: `PUT /cancelorder`
| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `OrderId` | `string` | 必須 | 注文番号 sendorderのレスポンスで受け取るOrderID。 |

---

## 8. PUSH API（WebSocket）の使い方

- 接続先: `/kabusapi/websocket`
- 配信は **値が更新されたタイミング**で流れる  
  ※場間（昼休み）や引け後は配信されない

### 8.1 配信を受けるまでの流れ
1) RESTで `POST /token`（トークン取得）  
2) RESTで `PUT /register`（配信したい銘柄を登録）  
3) WebSocket に接続して、JSONを受信

※登録できる銘柄は最大50銘柄（REST/PUSH合算）

---

## 9. よくあるハマりどころ（実務メモ）

- **kabuステにログインしていないと /token で 401 が出る**ことがある  
  → kabuステが起動＆ログイン済みか確認
- **トークンを再発行すると前のトークンは無効**になる  
  → 複数プロセス/複数端末で使う場合は設計注意
- 速度制限（429）に引っかかる  
  → バッチ照会は間隔を空ける、PUSHで代替する、など
- 50銘柄上限  
  → 監視銘柄を頻繁に切り替える場合は登録/解除をうまく回す

---

## 10. 次にやると最短で動く「最小構成」

1. `POST /token` でトークン取得  
2. `GET /board/{symbol}` で板・現在値を取る  
3. `GET /positions` で保有残高を取る  
4. `POST /sendorder` → `PUT /cancelorder` で発注・取消を試す  
5. `PUT /register` → WebSocket でリアルタイム受信

---

## Appendix: このMDの生成元

- OpenAPI YAML `kabu_STATION_API.yaml`（v1.5）
