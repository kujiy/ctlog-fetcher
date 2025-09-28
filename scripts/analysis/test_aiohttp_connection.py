"""
aiohttpのTCP接続監視コードの検証テスト
提供されたコードが正しく動作するかを検証します。
"""
import aiohttp
import asyncio
import time

async def fetch_with_connection_info(session, url, request_num):
    """
    提供されたコードをベースにしたfetch関数
    """
    try:
        async with session.get(url) as resp:
            # ソケット情報を取得
            conn = resp.connection
            if conn and conn.transport:
                sock = conn.transport.get_extra_info("socket")
                if sock:
                    local_port = sock.getsockname()[1]
                    peer_addr = sock.getpeername()
                    print(f"Request {request_num}: Local port: {local_port}, Remote: {peer_addr}")
                    return {
                        'request_num': request_num,
                        'local_port': local_port,
                        'peer_addr': peer_addr,
                        'status': resp.status,
                        'connection_reused': hasattr(conn, '_created_at')  # 追加情報
                    }
                else:
                    print(f"Request {request_num}: No socket available")
            else:
                print(f"Request {request_num}: No connection/transport available")
            
            return {
                'request_num': request_num,
                'local_port': None,
                'peer_addr': None,
                'status': resp.status
            }
    except Exception as e:
        print(f"Request {request_num}: Error - {e}")
        return {
            'request_num': request_num,
            'error': str(e)
        }

async def test_original_code():
    """
    提供されたオリジナルコードのテスト
    """
    print("=== オリジナルコードのテスト ===")
    
    async def fetch(session, url):
        async with session.get(url) as resp:
            # ソケット情報を取得
            conn = resp.connection
            sock = conn.transport.get_extra_info("socket")
            local_port = sock.getsockname()[1]
            print("Local port:", local_port)
            return await resp.text()

    async def main():
        async with aiohttp.ClientSession() as session:
            for i in range(5):
                await fetch(session, "https://httpbin.org/get")
                await asyncio.sleep(0.1)  # 少し待機

    try:
        await main()
    except Exception as e:
        print(f"オリジナルコードでエラー: {e}")

async def test_improved_code():
    """
    改良版のテスト（エラーハンドリング付き）
    """
    print("\n=== 改良版コードのテスト ===")
    
    results = []
    
    # テスト1: 同じセッションで連続リクエスト
    async with aiohttp.ClientSession() as session:
        print("Test 1: 同じセッションで連続リクエスト")
        for i in range(5):
            result = await fetch_with_connection_info(session, "https://httpbin.org/get", i+1)
            results.append(result)
            await asyncio.sleep(0.1)
    
    # テスト2: 異なるホストへのリクエスト
    async with aiohttp.ClientSession() as session:
        print("\nTest 2: 異なるホストへのリクエスト")
        urls = [
            "https://httpbin.org/get",
            "https://example.com",
            "https://httpbin.org/get",  # 再度同じホスト
        ]
        for i, url in enumerate(urls):
            result = await fetch_with_connection_info(session, url, i+1)
            results.append(result)
            await asyncio.sleep(0.1)
    
    # 結果の分析
    print("\n=== 結果の分析 ===")
    local_ports = [r.get('local_port') for r in results if r.get('local_port')]
    if local_ports:
        unique_ports = set(local_ports)
        print(f"使用されたローカルポート: {local_ports}")
        print(f"ユニークなポート数: {len(unique_ports)}")
        print(f"接続の再利用が確認できるか: {len(local_ports) > len(unique_ports)}")
    
    return results

async def test_connection_timeout():
    """
    接続タイムアウト時の動作テスト
    """
    print("\n=== 接続タイムアウトテスト ===")
    
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            # 短いタイムアウトでテスト
            result = await fetch_with_connection_info(session, "https://httpbin.org/delay/10", 1)
            print(f"タイムアウトテスト結果: {result}")
        except Exception as e:
            print(f"予想通りタイムアウト: {e}")

async def main():
    """
    メインテスト関数
    """
    print("aiohttpのTCP接続監視コードの検証を開始します...")
    
    # オリジナルコードのテスト
    await test_original_code()
    
    # 改良版のテスト
    results = await test_improved_code()
    
    # タイムアウトテスト
    await test_connection_timeout()
    
    print("\n=== 検証完了 ===")

if __name__ == "__main__":
    asyncio.run(main())
