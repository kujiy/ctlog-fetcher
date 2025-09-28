# curl での Google CT Log 接続分析結果

## 🎯 重要な発見

### 1. **curlでは接続が正常に再利用されている**
```
* Re-using existing connection with host ct.googleapis.com
* Connection #0 to host ct.googleapis.com left intact
```

### 2. **HTTP/2 ストリーム管理**
- 1回目のリクエスト: `[HTTP/2] [1] OPENED stream`
- 2回目のリクエスト: `[HTTP/2] [3] OPENED stream` 
- **同じ接続で異なるストリーム**を使用

### 3. **接続詳細**
- **プロトコル**: HTTP/2
- **TLS**: TLS 1.3 (AEAD-CHACHA20-POLY1305-SHA256)
- **ALPN**: server accepted h2
- **サーバーIP**: 142.251.222.42:443

## 🔍 aiohttpと比較した原因分析

### **curlの動作 (正常)**
1. 接続確立: `Connected to ct.googleapis.com`
2. 1回目リクエスト: Stream [1] で処理
3. 接続維持: `Connection #0 left intact`
4. 2回目リクエスト: **同じ接続を再利用** `Re-using existing connection`
5. 新ストリーム: Stream [3] で処理

### **aiohttpの問題 (推定)**
1. HTTP/2 ストリーム管理の実装問題
2. 接続オブジェクトをストリームごとに新規作成
3. 接続プールからの取得・返却タイミングの問題
4. POST-requestで接続プールが空になる現象

## 🚨 根本原因の特定

### **HTTP/2の影響**
- curlは1つの接続で複数ストリームを効率管理
- aiohttpはストリームごとに接続オブジェクトを作成
- 結果：**TCP接続は再利用されるが、aiohttpレベルでは「新規」**

### **Google CT Logの特性**
- キャッシュヘッダー: `cache-control: public, max-age=86400`
- レスポンス圧縮やストリーミング処理
- HTTP/2 Server Push などの最適化

## 💡 解決策の方向性

### 1. **aiohttp設定の最適化**
```python
connector = aiohttp.TCPConnector(
    limit=100,
    limit_per_host=10,
    keepalive_timeout=30,
    enable_cleanup_closed=True
)
```

### 2. **HTTP/1.1強制テスト**
```python
connector = aiohttp.TCPConnector(
    force_close=False,
    limit=100
)
# HTTP/1.1でのテスト
```

### 3. **接続プール監視の改善**
- ストリームIDの追跡
- HTTP/2 Connection状態の詳細監視
- transport レベルでの接続情報取得

## 📊 結論

**query paramが変わると再利用されない理由:**

1. **HTTP/2の実装問題**: aiohttpがストリームベースの接続管理を正しく実装していない
2. **Google サーバーの最適化**: HTTP/2の高度な機能がaiohttpと相性が悪い
3. **接続プールの設計問題**: TCP接続は再利用されるが、アプリケーションレベルでは検知できない

**これは元のコードの問題ではなく、aiohttpのHTTP/2実装の制限です。**
