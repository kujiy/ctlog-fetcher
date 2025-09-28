"""
ログファイルの正確な分析 - 接続再利用の実態を検証
"""

def analyze_log_data():
    """
    test_ct_log_incremental_params.log の正確な分析
    """
    print("=== 正確なログ分析 ===")
    
    # ログから抽出したデータ
    log_data = [
        # Test 1: 単一エントリリクエスト
        {"req": 1, "local_port": 62999, "conn_ids": [], "pool_before": {}, "pool_after": {}},
        {"req": 2, "local_port": 62999, "conn_ids": [4408873664], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        {"req": 3, "local_port": 62999, "conn_ids": [4408933888], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        {"req": 4, "local_port": 62999, "conn_ids": [4408933568], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        {"req": 5, "local_port": 62999, "conn_ids": [4408932544], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        {"req": 6, "local_port": 62999, "conn_ids": [4408933440], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        {"req": 7, "local_port": 62999, "conn_ids": [4408932352], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        {"req": 8, "local_port": 62999, "conn_ids": [4408932992], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        {"req": 9, "local_port": 62999, "conn_ids": [4408933952], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        {"req": 10, "local_port": 62999, "conn_ids": [4408933632], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        
        # Test 2: 範囲リクエスト (新しいセッション)
        {"req": 11, "local_port": 63003, "conn_ids": [], "pool_before": {}, "pool_after": {}},
        {"req": 12, "local_port": 63003, "conn_ids": [4408933632], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        {"req": 13, "local_port": 63003, "conn_ids": [4408835840], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        {"req": 14, "local_port": 63003, "conn_ids": [4408929216], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        {"req": 15, "local_port": 63003, "conn_ids": [4408930688], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        
        # Test 3: ランダムパラメータ (新しいセッション)  
        {"req": 16, "local_port": 63004, "conn_ids": [], "pool_before": {}, "pool_after": {}},
        {"req": 17, "local_port": 63004, "conn_ids": [4347640128], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        {"req": 18, "local_port": 63004, "conn_ids": [4408922432], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        {"req": 19, "local_port": 63004, "conn_ids": [4408932096], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
        {"req": 20, "local_port": 63004, "conn_ids": [4408932928], "pool_before": {"ct.googleapis.com": 1}, "pool_after": {}},
    ]
    
    print("1. ローカルポートの分析:")
    ports = set(req["local_port"] for req in log_data)
    print(f"   使用されたローカルポート: {sorted(ports)}")
    print(f"   ユニークポート数: {len(ports)}")
    
    # セッションごとの分析
    sessions = {
        62999: [req for req in log_data if req["local_port"] == 62999],
        63003: [req for req in log_data if req["local_port"] == 63003],
        63004: [req for req in log_data if req["local_port"] == 63004]
    }
    
    print("\n2. セッションごとの接続ID分析:")
    for port, session_reqs in sessions.items():
        print(f"\n   セッション (port {port}):")
        print(f"   リクエスト数: {len(session_reqs)}")
        
        all_conn_ids = []
        for req in session_reqs:
            if req["conn_ids"]:
                all_conn_ids.extend(req["conn_ids"])
        
        unique_conn_ids = set(all_conn_ids)
        print(f"   接続ID総数: {len(all_conn_ids)}")
        print(f"   ユニーク接続ID数: {len(unique_conn_ids)}")
        
        if len(all_conn_ids) > len(unique_conn_ids):
            print(f"   ✅ 接続ID再利用あり: {len(all_conn_ids) - len(unique_conn_ids)}回")
        else:
            print(f"   ❌ 接続ID再利用なし")
        
        # 接続IDの詳細
        for req in session_reqs[:5]:  # 最初の5個だけ表示
            if req["conn_ids"]:
                print(f"     Request {req['req']}: {req['conn_ids']}")
    
    print("\n3. 接続プール状態の分析:")
    print("   重要な観察:")
    print("   - Pre-request pool: 接続があることを示す")
    print("   - Post-request pool: 空 ({}) になっている")
    print("   - これは接続がプールから取り出され、使用後に戻されていない")
    
    print("\n4. 実際の問題点:")
    print("   ❌ Post-request poolが全て空になっている")
    print("   ❌ 接続IDが毎回変わっている")
    print("   ❌ 'No clear connection pattern' が大部分")
    print("   ❌ 'CONNECTION REUSED' や 'NEW CONNECTION detected' がない")
    
    print("\n5. 結論:")
    print("   ユーザーの指摘が正しい - 実際には接続の再利用が検知されていない")
    print("   同じローカルポート使用 ≠ 接続プールでの再利用")
    print("   TCPソケットは再利用されているが、aiohttpの接続プールレベルでは新規作成")

def explain_socket_vs_connection_pool():
    """
    ソケット再利用と接続プール再利用の違いを説明
    """
    print("\n" + "="*70)
    print("【ソケット再利用 vs 接続プール再利用の違い】")
    print("="*70)
    
    print("\n🔍 実際に起きていること:")
    print("1. TCPソケットレベル:")
    print("   ✅ 同じローカルポート (62999, 63003, 63004) を使用")
    print("   ✅ 同じリモートアドレス (142.251.222.42:443) に接続")
    print("   ✅ OS レベルでのTCP接続は効率的に管理されている")
    
    print("\n2. aiohttpの接続プールレベル:")
    print("   ❌ 接続オブジェクトのIDが毎回変わる")
    print("   ❌ Post-request poolが空になる")
    print("   ❌ 接続プールでの再利用が機能していない")
    
    print("\n🚨 元のコードの問題:")
    print("   元のコードは resp.connection.transport.get_extra_info('socket') で")
    print("   ソケット情報を取得しようとしていた")
    print("   → これは「TCPソケットの再利用」は検知できる")
    print("   → しかし「aiohttpの接続プール再利用」は検知できない")
    
    print("\n✅ 正しい理解:")
    print("   - TCPレベル: 効率的な接続管理が行われている")
    print("   - aiohttpレベル: 接続プールの再利用は限定的")
    print("   - 元のコード: どちらも正確に検知できない（エラーで停止）")

def final_conclusion():
    """
    最終的な結論
    """
    print("\n" + "="*70)
    print("【最終結論】")
    print("="*70)
    
    print("\n1. ユーザーの指摘は完全に正しい:")
    print("   ログを見る限り、aiohttpの接続プール再利用は検知されていない")
    
    print("\n2. 私の以前の分析の誤り:")
    print("   - 同じローカルポート = 接続プール再利用 と誤解した")
    print("   - TCPソケット再利用と接続プール再利用を混同した")
    
    print("\n3. 実際の状況:")
    print("   ✅ TCPソケット: 効率的に再利用されている")
    print("   ❌ aiohttp接続プール: 再利用が検知されない")
    print("   ❌ 元のコード: 両方とも正確に検知できない")
    
    print("\n4. 元のコードの検証結果（訂正）:")
    print("   - 元のコードはエラーで動作しない（これは正しい検証結果）")
    print("   - 修正版は動作するが、期待した接続プール再利用は検知できていない")
    print("   - ただし、TCPレベルでの効率的な接続は確認できている")

if __name__ == "__main__":
    analyze_log_data()
    explain_socket_vs_connection_pool()
    final_conclusion()
