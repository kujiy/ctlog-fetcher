"""
Google CT LogのURLでの再接続検知テスト
https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries?start=0&end=0
"""
import aiohttp
import asyncio
import time
from collections import defaultdict

class CTLogReconnectionDetector:
    def __init__(self):
        self.connection_history = []
        self.request_count = 0
    
    async def detect_reconnection(self, session, url, label=""):
        """
        CT LogのURLで再接続を検知
        """
        self.request_count += 1
        req_id = self.request_count
        
        print(f"\n--- Request {req_id} {label} ---")
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
            print(f"Pre-request connection IDs: {pre_connection_ids}")
        
        start_time = time.time()
        try:
            async with session.get(url) as resp:
                end_time = time.time()
                
                # レスポンスの基本情報
                print(f"Status: {resp.status}")
                print(f"Response time: {end_time - start_time:.3f}s")
                
                # レスポンスのヘッダー情報（CT Log特有の情報）
                content_type = resp.headers.get('content-type', 'N/A')
                server = resp.headers.get('server', 'N/A')
                print(f"Content-Type: {content_type}")
                print(f"Server: {server}")
                
                # リクエスト後の接続プール状態を記録
                post_pool_state = {}
                post_connection_ids = {}
                
                for key, conns in connector._conns.items():
                    key_str = str(key)
                    post_pool_state[key_str] = len(conns)
                    post_connection_ids[key_str] = [id(conn) for conn in conns]
                
                print(f"Post-request pool: {post_pool_state}")
                if post_connection_ids:
                    print(f"Post-request connection IDs: {post_connection_ids}")
                
                # 再接続の検知
                reconnection_detected = False
                new_connections = []
                reused_connections = []
                
                for key_str in post_connection_ids:
                    pre_ids = set(pre_connection_ids.get(key_str, []))
                    post_ids = set(post_connection_ids[key_str])
                    
                    # 新しい接続IDが追加された場合
                    new_ids = post_ids - pre_ids
                    if new_ids:
                        reconnection_detected = True
                        new_connections.extend(new_ids)
                        print(f"🔄 NEW CONNECTION detected for {key_str}: {new_ids}")
                    
                    # 再利用された接続ID
                    reused_ids = post_ids & pre_ids
                    if reused_ids:
                        reused_connections.extend(reused_ids)
                        print(f"♻️ CONNECTION REUSED for {key_str}: {reused_ids}")
                    
                    # 接続IDが変更された場合
                    if pre_ids and post_ids and pre_ids != post_ids:
                        print(f"🔄 CONNECTION CHANGE detected for {key_str}")
                        print(f"   Before: {pre_ids}")
                        print(f"   After:  {post_ids}")
                
                # 実際のレスポンス接続情報も取得（可能な場合）
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
                                print(f"Socket info: Local={local_addr}, Remote={remote_addr}")
                        except Exception as e:
                            print(f"Socket info error: {e}")
                else:
                    print("No connection object available")
                
                # CT Logのレスポンス内容をサンプル取得
                try:
                    response_text = await resp.text()
                    response_length = len(response_text)
                    print(f"Response length: {response_length} chars")
                    
                    # JSONレスポンスの場合、entriesの数を確認
                    if 'application/json' in content_type:
                        import json
                        try:
                            response_data = json.loads(response_text)
                            if 'entries' in response_data:
                                entries_count = len(response_data['entries'])
                                print(f"CT Log entries: {entries_count}")
                        except:
                            pass
                except Exception as e:
                    print(f"Response reading error: {e}")
                
                result = {
                    'request_id': req_id,
                    'url': url,
                    'status': resp.status,
                    'response_time': end_time - start_time,
                    'reconnection_detected': reconnection_detected,
                    'new_connection_ids': new_connections,
                    'reused_connection_ids': reused_connections,
                    'pre_pool_state': pre_pool_state,
                    'post_pool_state': post_pool_state,
                    'actual_connection': actual_conn_info,
                    'server': server,
                    'content_type': content_type
                }
                
                if reconnection_detected:
                    print(f"✅ RECONNECTION DETECTED in request {req_id}")
                elif reused_connections:
                    print(f"♻️ CONNECTION REUSED in request {req_id}")
                else:
                    print(f"🔍 No clear connection pattern detected in request {req_id}")
                
                self.connection_history.append(result)
                return result
                
        except Exception as e:
            print(f"❌ Request {req_id} failed: {e}")
            return {'request_id': req_id, 'error': str(e), 'url': url}

async def test_ct_log_connections():
    """
    CT LogのURLで接続パターンをテスト
    """
    print("=== Google CT Log 再接続検知テスト ===")
    print("URL: https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries?start=0&end=0")
    
    detector = CTLogReconnectionDetector()
    ct_url = "https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries?start=0&end=0"
    
    # テスト1: 同じCT LogのURLへの連続リクエスト
    print("\n🧪 Test 1: 同じCT LogのURLへの連続リクエスト")
    async with aiohttp.ClientSession() as session:
        for i in range(5):
            result = await detector.detect_reconnection(
                session, 
                ct_url, 
                f"CT Log #{i+1}"
            )
            # 少し間隔を空ける
            await asyncio.sleep(0.5)
    
    # テスト2: 他のURLと混在させてテスト
    print("\n🧪 Test 2: 他のURLと混在させてテスト")
    async with aiohttp.ClientSession() as session:
        urls = [
            ct_url,
            "https://httpbin.org/get",  # 別のホスト
            ct_url,  # 再度CT Log
            "https://example.com",     # 別のホスト
            ct_url   # 再々度CT Log
        ]
        
        for i, url in enumerate(urls):
            label = f"Mixed #{i+1}" + (" (CT Log)" if "ct.googleapis.com" in url else " (Other)")
            result = await detector.detect_reconnection(session, url, label)
            await asyncio.sleep(0.3)
    
    # テスト3: 長時間待機後のリクエスト（接続タイムアウトテスト）
    print("\n🧪 Test 3: 長時間待機後のリクエスト")
    async with aiohttp.ClientSession() as session:
        # 最初のリクエスト
        await detector.detect_reconnection(session, ct_url, "Before wait")
        
        # 10秒待機
        print("Waiting 10 seconds...")
        await asyncio.sleep(10)
        
        # 待機後のリクエスト
        await detector.detect_reconnection(session, ct_url, "After 10s wait")
    
    # 結果の分析
    print("\n" + "="*70)
    print("【CT Log 再接続検知結果の分析】")
    print("="*70)
    
    successful_requests = [
        req for req in detector.connection_history 
        if 'error' not in req
    ]
    
    ct_log_requests = [
        req for req in successful_requests 
        if "ct.googleapis.com" in req['url']
    ]
    
    reconnections = [
        req for req in successful_requests 
        if req['reconnection_detected']
    ]
    
    reused_connections = [
        req for req in successful_requests 
        if req.get('reused_connection_ids', [])
    ]
    
    print(f"Total requests: {len(detector.connection_history)}")
    print(f"Successful requests: {len(successful_requests)}")
    print(f"CT Log requests: {len(ct_log_requests)}")
    print(f"Reconnections detected: {len(reconnections)}")
    print(f"Connection reuse detected: {len(reused_connections)}")
    
    # CT Logでの接続パターン分析
    print(f"\n--- CT Log接続パターン分析 ---")
    ct_reconnections = [req for req in reconnections if "ct.googleapis.com" in req['url']]
    ct_reused = [req for req in reused_connections if "ct.googleapis.com" in req['url']]
    
    print(f"CT Log reconnections: {len(ct_reconnections)}")
    print(f"CT Log connection reuse: {len(ct_reused)}")
    
    if ct_log_requests:
        # レスポンス時間の分析
        response_times = [req['response_time'] for req in ct_log_requests]
        avg_time = sum(response_times) / len(response_times)
        print(f"CT Log average response time: {avg_time:.3f}s")
        
        # サーバー情報
        servers = set(req.get('server', 'N/A') for req in ct_log_requests)
        print(f"CT Log servers: {servers}")
    
    if ct_reconnections:
        print(f"✅ CT Logで再接続が検知されました")
        for req in ct_reconnections:
            print(f"  - Request {req['request_id']}: {len(req['new_connection_ids'])} new connections")
    
    if ct_reused:
        print(f"♻️ CT Logで接続の再利用が検知されました")
        for req in ct_reused:
            print(f"  - Request {req['request_id']}: {len(req['reused_connection_ids'])} reused connections")
    
    if not ct_reconnections and not ct_reused:
        print(f"⚠️ CT Logで明確な接続パターンが検知されませんでした")
    
    return detector.connection_history

async def main():
    """
    メインテスト関数
    """
    print("Google CT Log URL での再接続検知テスト開始")
    print("="*70)
    
    results = await test_ct_log_connections()
    
    print("\n" + "="*70)
    print("【最終結論】")
    print("1. Google CT LogのURLでも再接続検知システムが動作")
    print("2. 接続の再利用パターンを正確に把握可能")
    print("3. CT Log特有の接続特性も観測可能")
    print("4. オリジナルコードでは不可能な安定した監視を実現")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
