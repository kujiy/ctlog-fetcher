"""
aiohttpのTCP接続監視コード検証結果と修正版

【問題点の分析】
1. オリジナルコードで 'NoneType' object has no attribute 'transport' エラー
2. connection が None になるケースがある
3. transport が利用できないケースが多い

【修正版の提案】
"""
import aiohttp
import asyncio
import time

# 【問題のあるオリジナルコード】
async def problematic_original_code():
    """
    提供されたオリジナルコードの問題点を示す
    """
    async def fetch(session, url):
        async with session.get(url) as resp:
            # ❌ ここでエラーが発生する可能性
            conn = resp.connection
            sock = conn.transport.get_extra_info("socket")  # conn が None の場合エラー
            local_port = sock.getsockname()[1]
            print("Local port:", local_port)
            return await resp.text()

    async with aiohttp.ClientSession() as session:
        try:
            await fetch(session, "https://httpbin.org/get")
        except Exception as e:
            print(f"オリジナルコードのエラー: {e}")

# 【修正版1: 基本的なエラーハンドリング】
async def improved_version_1():
    """
    基本的なエラーハンドリングを追加した修正版
    """
    print("=== 修正版1: 基本的なエラーハンドリング ===")
    
    async def safe_fetch(session, url, request_id):
        async with session.get(url) as resp:
            conn = resp.connection
            
            if conn is None:
                print(f"Request {request_id}: Connection is None")
                return None
            
            if not hasattr(conn, 'transport') or conn.transport is None:
                print(f"Request {request_id}: Transport not available")
                return None
            
            sock = conn.transport.get_extra_info("socket")
            if sock is None:
                print(f"Request {request_id}: Socket not available")
                return None
            
            local_port = sock.getsockname()[1]
            peer_addr = sock.getpeername()
            print(f"Request {request_id}: Local port: {local_port}, Remote: {peer_addr}")
            
            return {
                'local_port': local_port,
                'peer_addr': peer_addr,
                'status': resp.status
            }

    async with aiohttp.ClientSession() as session:
        for i in range(3):
            result = await safe_fetch(session, "https://httpbin.org/get", i+1)
            await asyncio.sleep(0.1)

# 【修正版2: より堅牢なアプローチ】
async def improved_version_2():
    """
    より堅牢で実用的な接続監視アプローチ
    """
    print("\n=== 修正版2: より堅牢なアプローチ ===")
    
    class ConnectionTracker:
        def __init__(self):
            self.connection_info = {}
            self.request_count = 0
        
        async def track_request(self, session, url):
            self.request_count += 1
            request_id = self.request_count
            
            start_time = time.time()
            try:
                async with session.get(url) as resp:
                    end_time = time.time()
                    
                    connection_data = {
                        'request_id': request_id,
                        'url': url,
                        'status': resp.status,
                        'response_time': end_time - start_time,
                        'connection_available': False,
                        'local_port': None,
                        'remote_addr': None,
                        'socket_id': None,
                        'connection_id': None
                    }
                    
                    # 安全に接続情報を取得
                    conn = resp.connection
                    if conn:
                        connection_data['connection_available'] = True
                        connection_data['connection_id'] = id(conn)
                        
                        if hasattr(conn, 'transport') and conn.transport:
                            sock = conn.transport.get_extra_info("socket")
                            if sock:
                                try:
                                    local_addr = sock.getsockname()
                                    remote_addr = sock.getpeername()
                                    connection_data.update({
                                        'local_port': local_addr[1],
                                        'local_ip': local_addr[0],
                                        'remote_addr': remote_addr,
                                        'socket_id': id(sock)
                                    })
                                except Exception as e:
                                    print(f"Socket info error: {e}")
                    
                    print(f"Request {request_id}: "
                          f"Port={connection_data['local_port']}, "
                          f"Status={connection_data['status']}, "
                          f"Time={connection_data['response_time']:.3f}s")
                    
                    self.connection_info[request_id] = connection_data
                    return connection_data
                    
            except Exception as e:
                print(f"Request {request_id} failed: {e}")
                return {'request_id': request_id, 'error': str(e)}
        
        def analyze_connections(self):
            """接続の再利用状況を分析"""
            print("\n--- 接続分析結果 ---")
            successful_requests = [
                info for info in self.connection_info.values() 
                if 'error' not in info and info['local_port']
            ]
            
            if not successful_requests:
                print("接続情報を取得できたリクエストがありません")
                return
            
            local_ports = [req['local_port'] for req in successful_requests]
            socket_ids = [req['socket_id'] for req in successful_requests]
            connection_ids = [req['connection_id'] for req in successful_requests]
            
            print(f"Total requests: {len(self.connection_info)}")
            print(f"Successful port captures: {len(local_ports)}")
            print(f"Local ports used: {local_ports}")
            print(f"Unique ports: {len(set(local_ports))}")
            print(f"Unique socket IDs: {len(set(socket_ids))}")
            print(f"Unique connection IDs: {len(set(connection_ids))}")
            
            if len(set(local_ports)) < len(local_ports):
                print("✅ 接続の再利用が確認されました")
            else:
                print("⚠️  接続の再利用が確認されませんでした")

    tracker = ConnectionTracker()
    
    # テスト1: 同じホストへの連続リクエスト
    async with aiohttp.ClientSession() as session:
        print("同じホストへの連続リクエスト:")
        for i in range(5):
            await tracker.track_request(session, "https://httpbin.org/get")
            await asyncio.sleep(0.1)
    
    # テスト2: 異なるホストへのリクエスト
    async with aiohttp.ClientSession() as session:
        print("\n異なるホストへのリクエスト:")
        urls = [
            "https://httpbin.org/get",
            "https://example.com",
            "https://httpbin.org/status/200"
        ]
        for url in urls:
            await tracker.track_request(session, url)
            await asyncio.sleep(0.1)
    
    tracker.analyze_connections()

# 【修正版3: 接続プールの直接監視】
async def improved_version_3():
    """
    接続プールを直接監視するアプローチ
    """
    print("\n=== 修正版3: 接続プールの直接監視 ===")
    
    connector = aiohttp.TCPConnector()
    
    async with aiohttp.ClientSession(connector=connector) as session:
        print("接続プールの初期状態:")
        print(f"Pool keys: {list(connector._conns.keys())}")
        
        for i in range(3):
            print(f"\n--- Request {i+1} ---")
            async with session.get("https://httpbin.org/get") as resp:
                print(f"Status: {resp.status}")
                
                # プールの状態を確認
                pool_state = {}
                for key, conns in connector._conns.items():
                    pool_state[str(key)] = len(conns)
                print(f"Pool state: {pool_state}")
                
                # 利用可能な接続数
                total_connections = sum(len(conns) for conns in connector._conns.values())
                print(f"Total pooled connections: {total_connections}")
            
            await asyncio.sleep(0.1)

async def main():
    """
    全ての修正版をテスト
    """
    print("aiohttpのTCP接続監視コード - 問題点と修正版の検証\n")
    
    # 問題のあるオリジナルコード
    await problematic_original_code()
    
    # 修正版のテスト
    await improved_version_1()
    await improved_version_2()
    await improved_version_3()
    
    print("\n" + "="*60)
    print("【結論】")
    print("1. オリジナルコードは connection が None になる場合にエラーが発生")
    print("2. transport が利用できないケースが多く存在")
    print("3. エラーハンドリングが必須")
    print("4. 接続の再利用は発生するが、情報取得が不安定")
    print("5. より堅牢なアプローチが必要")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
