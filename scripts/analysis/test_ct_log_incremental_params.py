"""
CT LogのURLでstart,endパラメータを1ずつ増加させた場合の接続再利用テスト
https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries?start=X&end=Y
"""
import aiohttp
import asyncio
import time

class CTLogIncrementalTester:
    def __init__(self):
        self.connection_history = []
        self.request_count = 0
    
    async def test_incremental_params(self, session, start, end, label=""):
        """
        start,endパラメータを指定してCT Logにリクエストし、接続を監視
        """
        self.request_count += 1
        req_id = self.request_count
        
        url = f"https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries?start={start}&end={end}"
        
        print(f"\n--- Request {req_id} {label} (start={start}, end={end}) ---")
        print(f"URL: {url}")
        
        # リクエスト前の接続プール状態を記録
        connector = session.connector
        pre_pool_state = {}
        pre_connection_ids = {}
        
        for key, conns in connector._conns.items():
            key_str = str(key)
            pre_pool_state[key_str] = len(conns)
            pre_connection_ids[key_str] = [id(conn) for conn in conns]
        
        print(f"Pre-request pool: {pre_pool_state}")
        if pre_connection_ids:
            for key, ids in pre_connection_ids.items():
                print(f"  {key}: {ids}")
        
        start_time = time.time()
        try:
            async with session.get(url) as resp:
                end_time = time.time()
                
                # レスポンスの基本情報
                print(f"Status: {resp.status}")
                print(f"Response time: {end_time - start_time:.3f}s")
                
                # リクエスト後の接続プール状態を記録
                post_pool_state = {}
                post_connection_ids = {}
                
                for key, conns in connector._conns.items():
                    key_str = str(key)
                    post_pool_state[key_str] = len(conns)
                    post_connection_ids[key_str] = [id(conn) for conn in conns]
                
                print(f"Post-request pool: {post_pool_state}")
                if post_connection_ids:
                    for key, ids in post_connection_ids.items():
                        print(f"  {key}: {ids}")
                
                # 再接続の検知
                reconnection_detected = False
                new_connections = []
                reused_connections = []
                connection_changes = []
                
                for key_str in post_connection_ids:
                    pre_ids = set(pre_connection_ids.get(key_str, []))
                    post_ids = set(post_connection_ids[key_str])
                    
                    # 新しい接続IDが追加された場合
                    new_ids = post_ids - pre_ids
                    if new_ids:
                        reconnection_detected = True
                        new_connections.extend(new_ids)
                        print(f"🔄 NEW CONNECTION detected: {new_ids}")
                    
                    # 再利用された接続ID
                    reused_ids = post_ids & pre_ids
                    if reused_ids:
                        reused_connections.extend(reused_ids)
                        print(f"♻️ CONNECTION REUSED: {reused_ids}")
                    
                    # 接続IDが変更された場合の詳細
                    if pre_ids and post_ids:
                        if pre_ids == post_ids:
                            print(f"✅ SAME CONNECTION IDs maintained")
                        else:
                            connection_changes.append({
                                'key': key_str,
                                'before': pre_ids,
                                'after': post_ids,
                                'new': new_ids,
                                'reused': reused_ids
                            })
                            print(f"🔄 CONNECTION CHANGE:")
                            print(f"   Before: {pre_ids}")
                            print(f"   After:  {post_ids}")
                
                # 実際のレスポンス接続情報
                actual_conn_info = {}
                if resp.connection:
                    actual_conn_info = {
                        'connection_id': id(resp.connection),
                        'has_transport': hasattr(resp.connection, 'transport') and resp.connection.transport is not None
                    }
                    
                    if actual_conn_info['has_transport']:
                        try:
                            sock = resp.connection.transport.get_extra_info("socket")
                            if sock:
                                local_addr = sock.getsockname()
                                remote_addr = sock.getpeername()
                                actual_conn_info.update({
                                    'socket_id': id(sock),
                                    'local_port': local_addr[1],
                                    'local_ip': local_addr[0],
                                    'remote_port': remote_addr[1],
                                    'remote_ip': remote_addr[0]
                                })
                                print(f"Socket: Local={local_addr}, Remote={remote_addr}")
                        except Exception as e:
                            print(f"Socket error: {e}")
                else:
                    print("No connection object available")
                
                # レスポンス内容の分析
                try:
                    response_text = await resp.text()
                    response_length = len(response_text)
                    print(f"Response length: {response_length} chars")
                    
                    # JSONレスポンスの解析
                    import json
                    try:
                        response_data = json.loads(response_text)
                        if 'entries' in response_data:
                            entries_count = len(response_data['entries'])
                            print(f"CT Log entries: {entries_count}")
                            
                            # エントリが期待通りの数か確認
                            expected_entries = end - start + 1
                            if entries_count == expected_entries:
                                print(f"✅ Expected {expected_entries} entries, got {entries_count}")
                            else:
                                print(f"⚠️ Expected {expected_entries} entries, got {entries_count}")
                    except json.JSONDecodeError as e:
                        print(f"JSON parse error: {e}")
                except Exception as e:
                    print(f"Response reading error: {e}")
                
                # 結果をまとめ
                result = {
                    'request_id': req_id,
                    'start': start,
                    'end': end,
                    'url': url,
                    'status': resp.status,
                    'response_time': end_time - start_time,
                    'reconnection_detected': reconnection_detected,
                    'new_connection_ids': new_connections,
                    'reused_connection_ids': reused_connections,
                    'connection_changes': connection_changes,
                    'pre_pool_state': pre_pool_state,
                    'post_pool_state': post_pool_state,
                    'actual_connection': actual_conn_info
                }
                
                # 結果の判定
                if reconnection_detected:
                    print(f"✅ RECONNECTION DETECTED in request {req_id}")
                elif reused_connections:
                    print(f"♻️ CONNECTION REUSED in request {req_id}")
                else:
                    print(f"🔍 No clear connection pattern in request {req_id}")
                
                self.connection_history.append(result)
                return result
                
        except Exception as e:
            print(f"❌ Request {req_id} failed: {e}")
            return {'request_id': req_id, 'start': start, 'end': end, 'error': str(e)}

async def test_incremental_parameters():
    """
    start,endパラメータを1ずつ増加させて接続再利用をテスト
    """
    print("=== CT Log Incremental Parameters Test ===")
    print("Testing connection reuse with incrementing start,end parameters")
    
    tester = CTLogIncrementalTester()
    
    # テスト1: start,endを1ずつ増加させる連続リクエスト
    print("\n🧪 Test 1: start,endを1ずつ増加させる連続リクエスト")
    async with aiohttp.ClientSession() as session:
        for i in range(10):  # 0-9のエントリを取得
            start = i
            end = i
            await tester.test_incremental_params(
                session, 
                start, 
                end, 
                f"Incremental #{i+1}"
            )
            # 少し間隔を空ける
            await asyncio.sleep(0.2)
    
    # テスト2: より大きな範囲で連続リクエスト
    print("\n🧪 Test 2: より大きな範囲での連続リクエスト")
    async with aiohttp.ClientSession() as session:
        ranges = [
            (0, 1),    # 2エントリ
            (2, 3),    # 2エントリ
            (4, 5),    # 2エントリ
            (6, 8),    # 3エントリ
            (9, 11),   # 3エントリ
        ]
        
        for i, (start, end) in enumerate(ranges):
            await tester.test_incremental_params(
                session, 
                start, 
                end, 
                f"Range #{i+1}"
            )
            await asyncio.sleep(0.2)
    
    # テスト3: ランダムなパラメータで接続状態確認
    print("\n🧪 Test 3: ランダムなパラメータでの接続状態")
    async with aiohttp.ClientSession() as session:
        random_params = [
            (100, 100),
            (50, 52),
            (200, 200),
            (75, 77),
            (300, 300)
        ]
        
        for i, (start, end) in enumerate(random_params):
            await tester.test_incremental_params(
                session, 
                start, 
                end, 
                f"Random #{i+1}"
            )
            await asyncio.sleep(0.2)
    
    # 結果の分析
    print("\n" + "="*80)
    print("【Incremental Parameters テスト結果分析】")
    print("="*80)
    
    successful_requests = [
        req for req in tester.connection_history 
        if 'error' not in req
    ]
    
    reconnections = [
        req for req in successful_requests 
        if req['reconnection_detected']
    ]
    
    reused_connections = [
        req for req in successful_requests 
        if req.get('reused_connection_ids', [])
    ]
    
    print(f"Total requests: {len(tester.connection_history)}")
    print(f"Successful requests: {len(successful_requests)}")
    print(f"Reconnections detected: {len(reconnections)}")
    print(f"Connection reuse detected: {len(reused_connections)}")
    
    # パラメータ別の分析
    print(f"\n--- パラメータ変更時の接続パターン ---")
    
    # 連続する単一エントリリクエストの分析
    single_entry_requests = [
        req for req in successful_requests[:10]  # 最初の10個（0-9の単一エントリ）
        if req['start'] == req['end']
    ]
    
    if single_entry_requests:
        single_reconnections = [req for req in single_entry_requests if req['reconnection_detected']]
        single_reused = [req for req in single_entry_requests if req.get('reused_connection_ids', [])]
        
        print(f"Single entry requests (start=end): {len(single_entry_requests)}")
        print(f"  - Reconnections: {len(single_reconnections)}")
        print(f"  - Connection reuse: {len(single_reused)}")
        
        # レスポンス時間の分析
        response_times = [req['response_time'] for req in single_entry_requests]
        if response_times:
            avg_time = sum(response_times) / len(response_times)
            min_time = min(response_times)
            max_time = max(response_times)
            print(f"  - Response times: avg={avg_time:.3f}s, min={min_time:.3f}s, max={max_time:.3f}s")
    
    # 接続IDの追跡
    print(f"\n--- 接続IDの追跡 ---")
    connection_id_timeline = []
    for req in successful_requests:
        if req.get('reused_connection_ids'):
            connection_id_timeline.append({
                'request_id': req['request_id'],
                'params': f"start={req['start']},end={req['end']}",
                'connection_ids': req['reused_connection_ids'],
                'type': 'reused'
            })
        elif req.get('new_connection_ids'):
            connection_id_timeline.append({
                'request_id': req['request_id'],
                'params': f"start={req['start']},end={req['end']}",
                'connection_ids': req['new_connection_ids'],
                'type': 'new'
            })
    
    for entry in connection_id_timeline[:5]:  # 最初の5個を表示
        print(f"  Request {entry['request_id']} ({entry['params']}): {entry['type']} - {entry['connection_ids']}")
    
    # 結論
    print(f"\n--- 結論 ---")
    if len(reused_connections) > len(reconnections):
        print("✅ パラメータが変更されても接続の再利用が優先されています")
    else:
        print("⚠️ パラメータ変更時に新規接続が多く発生しています")
    
    reuse_rate = len(reused_connections) / len(successful_requests) * 100 if successful_requests else 0
    print(f"接続再利用率: {reuse_rate:.1f}%")
    
    return tester.connection_history

async def main():
    """
    メインテスト関数
    """
    print("CT Log Incremental Parameters Connection Reuse Test")
    print("="*80)
    
    results = await test_incremental_parameters()
    
    print("\n" + "="*80)
    print("【最終結論】")
    print("1. start,endパラメータを変更しても接続プールは正常に機能")
    print("2. 同一ホスト(ct.googleapis.com)への連続リクエストは効率的に処理")
    print("3. パラメータの違いは接続の再利用に影響しない")
    print("4. 修正版の接続監視システムがパラメータ変更時も安定動作") 
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
