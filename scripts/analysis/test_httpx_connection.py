"""
httpxでの接続プール動作テスト
aiohttpがHTTP/2非対応のため、HTTP/2対応のhttpxで検証
"""
import httpx
import asyncio
import time

class HTTPXConnectionTester:
    def __init__(self):
        self.connection_history = []
        self.request_count = 0
    
    async def test_connection_reuse(self, client, url, label=""):
        """
        httpxでの接続再利用テスト
        """
        self.request_count += 1
        req_id = self.request_count
        
        print(f"\n--- Request {req_id} {label} ---")
        print(f"URL: {url}")
        
        start_time = time.time()
        try:
            response = await client.get(url)
            end_time = time.time()
            
            # レスポンス情報
            print(f"Status: {response.status_code}")
            print(f"Response time: {end_time - start_time:.3f}s")
            print(f"HTTP Version: {response.http_version}")
            
            # ヘッダー情報
            print(f"Content-Type: {response.headers.get('content-type', 'N/A')}")
            print(f"Content-Length: {response.headers.get('content-length', 'N/A')}")
            
            # レスポンス内容の確認
            response_text = response.text
            response_length = len(response_text)
            print(f"Response length: {response_length} chars")
            
            # JSON解析
            try:
                import json
                response_data = json.loads(response_text)
                if 'entries' in response_data:
                    entries_count = len(response_data['entries'])
                    print(f"CT Log entries: {entries_count}")
            except:
                pass
            
            result = {
                'request_id': req_id,
                'url': url,
                'status': response.status_code,
                'response_time': end_time - start_time,
                'http_version': response.http_version,
                'content_length': response_length,
                'headers': dict(response.headers)
            }
            
            self.connection_history.append(result)
            return result
                
        except Exception as e:
            print(f"❌ Request {req_id} failed: {e}")
            return {'request_id': req_id, 'error': str(e), 'url': url}

async def test_httpx_incremental_params():
    """
    httpxでstart,endパラメータを変更した接続再利用テスト
    """
    print("=== HTTPX Connection Pool Test ===")
    print("Testing HTTP/2 connection reuse with incrementing parameters")
    
    tester = HTTPXConnectionTester()
    
    # HTTP/2対応の設定
    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
    timeout = httpx.Timeout(30.0)
    
    # テスト1: HTTP/2での接続プール動作
    print("\n🧪 Test 1: HTTP/2での連続リクエスト")
    async with httpx.AsyncClient(
        limits=limits, 
        timeout=timeout,
        http2=True  # HTTP/2を有効化
    ) as client:
        
        for i in range(5):
            url = f"https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries?start={i}&end={i}"
            await tester.test_connection_reuse(client, url, f"HTTP/2 #{i+1}")
            await asyncio.sleep(0.2)
    
    # テスト2: HTTP/1.1での接続プール動作（比較用）
    print("\n🧪 Test 2: HTTP/1.1での連続リクエスト")
    async with httpx.AsyncClient(
        limits=limits, 
        timeout=timeout,
        http2=False  # HTTP/1.1を強制
    ) as client:
        
        for i in range(5):
            url = f"https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries?start={i+5}&end={i+5}"
            await tester.test_connection_reuse(client, url, f"HTTP/1.1 #{i+1}")
            await asyncio.sleep(0.2)
    
    # 結果の分析
    print("\n" + "="*70)
    print("【HTTPX 接続プール分析結果】")
    print("="*70)
    
    successful_requests = [
        req for req in tester.connection_history 
        if 'error' not in req
    ]
    
    http2_requests = [
        req for req in successful_requests 
        if req.get('http_version') == 'HTTP/2'
    ]
    
    http11_requests = [
        req for req in successful_requests 
        if req.get('http_version') == 'HTTP/1.1'
    ]
    
    print(f"Total requests: {len(tester.connection_history)}")
    print(f"Successful requests: {len(successful_requests)}")
    print(f"HTTP/2 requests: {len(http2_requests)}")
    print(f"HTTP/1.1 requests: {len(http11_requests)}")
    
    # レスポンス時間の分析
    if http2_requests:
        http2_times = [req['response_time'] for req in http2_requests]
        avg_http2 = sum(http2_times) / len(http2_times)
        print(f"HTTP/2 average response time: {avg_http2:.3f}s")
        print(f"HTTP/2 times: {[f'{t:.3f}' for t in http2_times]}")
    
    if http11_requests:
        http11_times = [req['response_time'] for req in http11_requests]
        avg_http11 = sum(http11_times) / len(http11_times)
        print(f"HTTP/1.1 average response time: {avg_http11:.3f}s")
        print(f"HTTP/1.1 times: {[f'{t:.3f}' for t in http11_times]}")
    
    # 接続効率の分析
    print("\n--- 接続効率分析 ---")
    if http2_requests and len(http2_requests) > 1:
        first_http2 = http2_requests[0]['response_time']
        subsequent_http2 = [req['response_time'] for req in http2_requests[1:]]
        avg_subsequent_http2 = sum(subsequent_http2) / len(subsequent_http2)
        
        improvement_http2 = ((first_http2 - avg_subsequent_http2) / first_http2) * 100
        print(f"HTTP/2 connection reuse improvement: {improvement_http2:.1f}%")
        print(f"  First request: {first_http2:.3f}s")
        print(f"  Subsequent avg: {avg_subsequent_http2:.3f}s")
    
    if http11_requests and len(http11_requests) > 1:
        first_http11 = http11_requests[0]['response_time']
        subsequent_http11 = [req['response_time'] for req in http11_requests[1:]]
        avg_subsequent_http11 = sum(subsequent_http11) / len(subsequent_http11)
        
        improvement_http11 = ((first_http11 - avg_subsequent_http11) / first_http11) * 100
        print(f"HTTP/1.1 connection reuse improvement: {improvement_http11:.1f}%")
        print(f"  First request: {first_http11:.3f}s")
        print(f"  Subsequent avg: {avg_subsequent_http11:.3f}s")
    
    return tester.connection_history

async def test_httpx_connection_pool_detailed():
    """
    httpxの接続プール詳細テスト
    """
    print("\n🧪 Test 3: 接続プール詳細動作")
    
    tester = HTTPXConnectionTester()
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    
    async with httpx.AsyncClient(limits=limits, http2=True) as client:
        # 同一URLでの連続リクエスト
        same_url = "https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries?start=0&end=0"
        
        print("同一URLでの連続リクエスト:")
        for i in range(3):
            await tester.test_connection_reuse(client, same_url, f"Same URL #{i+1}")
            await asyncio.sleep(0.1)
        
        # 異なるパラメータでの連続リクエスト
        print("\n異なるパラメータでの連続リクエスト:")
        for i in range(3):
            url = f"https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries?start={i+10}&end={i+10}"
            await tester.test_connection_reuse(client, url, f"Different param #{i+1}")
            await asyncio.sleep(0.1)

async def main():
    """
    メイン関数
    """
    print("HTTPX HTTP/2 Connection Pool Test")
    print("="*70)
    
    # 基本テスト
    await test_httpx_incremental_params()
    
    # 詳細テスト
    await test_httpx_connection_pool_detailed()
    
    print("\n" + "="*70)
    print("【最終結論】")
    print("1. httpxはHTTP/2に対応している")
    print("2. HTTP/2とHTTP/1.1での接続プール動作を比較可能")
    print("3. query parameterが変わっても接続プールが正常に動作するか検証")
    print("4. aiohttpの問題がHTTP/2非対応によるものかを確認")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
