"""
httpx + HTTP/2での長時間待機後の接続維持と自動再接続テスト
180秒のsleep後に接続が維持されるか、切れた場合の自動再接続を検証
"""
import httpx
import asyncio
import time
import logging

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LongIdleConnectionTester:
    def __init__(self):
        self.connection_history = []
        self.request_count = 0
    
    async def test_request_with_timing(self, client, url, label=""):
        """
        詳細なタイミング情報付きでリクエストをテスト
        """
        self.request_count += 1
        req_id = self.request_count
        
        print(f"\n--- Request {req_id} {label} ---")
        print(f"Time: {time.strftime('%H:%M:%S')}")
        print(f"URL: {url}")
        
        start_time = time.time()
        try:
            # リクエスト実行
            response = await client.get(url)
            end_time = time.time()
            
            # レスポンス情報
            print(f"Status: {response.status_code}")
            print(f"Response time: {end_time - start_time:.3f}s")
            print(f"HTTP Version: {response.http_version}")
            
            # 接続関連ヘッダーの確認
            connection_headers = {}
            for header in ['connection', 'keep-alive', 'server', 'date']:
                if header in response.headers:
                    connection_headers[header] = response.headers[header]
                    print(f"{header}: {response.headers[header]}")
            
            # レスポンス内容の確認
            response_text = response.text
            response_length = len(response_text)
            print(f"Response length: {response_length} chars")
            
            # JSON解析（CT Log特有）
            entries_count = 0
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
                'timestamp': time.time(),
                'url': url,
                'status': response.status_code,
                'response_time': end_time - start_time,
                'http_version': response.http_version,
                'content_length': response_length,
                'entries_count': entries_count,
                'connection_headers': connection_headers,
                'success': True
            }
            
            self.connection_history.append(result)
            return result
                
        except Exception as e:
            end_time = time.time()
            print(f"❌ Request {req_id} failed: {e}")
            print(f"Error type: {type(e).__name__}")
            print(f"Failed after: {end_time - start_time:.3f}s")
            
            result = {
                'request_id': req_id,
                'timestamp': time.time(),
                'url': url,
                'error': str(e),
                'error_type': type(e).__name__,
                'response_time': end_time - start_time,
                'success': False
            }
            
            self.connection_history.append(result)
            return result

async def test_long_idle_connection():
    """
    180秒待機後の接続維持・自動再接続テスト
    """
    print("=== Long Idle Connection Test (180 seconds) ===")
    print("Testing connection persistence and auto-reconnection")
    
    tester = LongIdleConnectionTester()
    
    # 接続設定
    limits = httpx.Limits(
        max_keepalive_connections=5, 
        max_connections=10,
        keepalive_expiry=300  # 5分のkeep-alive
    )
    timeout = httpx.Timeout(30.0)
    
    async with httpx.AsyncClient(
        limits=limits, 
        timeout=timeout,
        http2=True
    ) as client:
        
        base_url = "https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries"
        
        # Phase 1: 初期接続の確立
        print("\n🔵 Phase 1: 初期接続の確立")
        await tester.test_request_with_timing(
            client, 
            f"{base_url}?start=0&end=0", 
            "Initial connection"
        )
        
        # Phase 2: 短時間待機後のリクエスト（接続維持確認）
        print("\n🔵 Phase 2: 短時間待機後（5秒）")
        await asyncio.sleep(5)
        await tester.test_request_with_timing(
            client, 
            f"{base_url}?start=1&end=1", 
            "After 5s wait"
        )
        
        # Phase 3: 中程度待機後のリクエスト（30秒）
        print("\n🔵 Phase 3: 中程度待機後（30秒）") 
        print("Waiting 30 seconds...")
        await asyncio.sleep(30)
        await tester.test_request_with_timing(
            client, 
            f"{base_url}?start=2&end=2", 
            "After 30s wait"
        )
        
        # Phase 4: 長時間待機後のリクエスト（180秒）
        print("\n🔵 Phase 4: 長時間待機後（180秒）")
        print("Waiting 180 seconds... (3 minutes)")
        print("This will test connection timeout and auto-reconnection...")
        
        # 180秒を分割して進捗表示
        for i in range(18):
            await asyncio.sleep(10)
            remaining = 180 - (i + 1) * 10
            if remaining > 0:
                print(f"... {remaining} seconds remaining")
        
        # 長時間待機後のリクエスト
        await tester.test_request_with_timing(
            client, 
            f"{base_url}?start=3&end=3", 
            "After 180s wait (3 minutes)"
        )
        
        # Phase 5: 再接続後の連続リクエスト
        print("\n🔵 Phase 5: 再接続後の連続リクエスト")
        for i in range(3):
            await tester.test_request_with_timing(
                client, 
                f"{base_url}?start={i+4}&end={i+4}", 
                f"Post-reconnection #{i+1}"
            )
            await asyncio.sleep(1)
    
    # 結果の分析
    analyze_connection_behavior(tester.connection_history)
    
    return tester.connection_history

def analyze_connection_behavior(history):
    """
    接続動作の詳細分析
    """
    print("\n" + "="*80)
    print("【長時間待機接続テスト結果分析】")
    print("="*80)
    
    successful_requests = [req for req in history if req.get('success', False)]
    failed_requests = [req for req in history if not req.get('success', False)]
    
    print(f"Total requests: {len(history)}")
    print(f"Successful requests: {len(successful_requests)}")
    print(f"Failed requests: {len(failed_requests)}")
    
    if failed_requests:
        print(f"\n--- 失敗したリクエスト ---")
        for req in failed_requests:
            print(f"Request {req['request_id']}: {req.get('error_type', 'Unknown')} - {req.get('error', 'No details')}")
    
    # レスポンス時間の分析
    if successful_requests:
        print(f"\n--- レスポンス時間分析 ---")
        
        # フェーズ別の分析
        phases = {
            'Initial': [req for req in successful_requests if req['request_id'] == 1],
            'After 5s': [req for req in successful_requests if req['request_id'] == 2], 
            'After 30s': [req for req in successful_requests if req['request_id'] == 3],
            'After 180s': [req for req in successful_requests if req['request_id'] == 4],
            'Post-reconnection': [req for req in successful_requests if req['request_id'] >= 5]
        }
        
        for phase_name, requests in phases.items():
            if requests:
                times = [req['response_time'] for req in requests]
                avg_time = sum(times) / len(times)
                print(f"{phase_name}: {avg_time:.3f}s (requests: {len(requests)})")
                
                # 詳細情報
                for req in requests:
                    print(f"  Request {req['request_id']}: {req['response_time']:.3f}s, {req['http_version']}")
    
    # 接続維持の判定
    print(f"\n--- 接続維持判定 ---")
    
    # 初回と180秒後のレスポンス時間を比較
    initial_req = next((req for req in successful_requests if req['request_id'] == 1), None)
    long_wait_req = next((req for req in successful_requests if req['request_id'] == 4), None)
    
    if initial_req and long_wait_req:
        initial_time = initial_req['response_time']
        long_wait_time = long_wait_req['response_time']
        
        print(f"初回リクエスト: {initial_time:.3f}s")
        print(f"180秒後リクエスト: {long_wait_time:.3f}s")
        
        # 再接続の判定（レスポンス時間が大幅に増加した場合）
        if long_wait_time > initial_time * 2:
            print("🔄 判定: 接続が切断され、自動再接続が発生した可能性が高い")
            print(f"   レスポンス時間増加: {((long_wait_time - initial_time) / initial_time * 100):.1f}%")
        elif long_wait_time <= initial_time * 1.2:
            print("✅ 判定: 接続が維持されている可能性が高い")
            print(f"   レスポンス時間変化: {((long_wait_time - initial_time) / initial_time * 100):.1f}%")
        else:
            print("⚠️ 判定: 接続状態が不明確")
    
    # HTTP/2の動作確認
    http2_requests = [req for req in successful_requests if req.get('http_version') == 'HTTP/2']
    print(f"\nHTTP/2 requests: {len(http2_requests)}/{len(successful_requests)}")
    
    if len(http2_requests) == len(successful_requests):
        print("✅ 全リクエストでHTTP/2が使用されている")
    else:
        print("⚠️ HTTP/2が一貫して使用されていない")

async def test_multiple_long_waits():
    """
    複数回の長時間待機テスト（短縮版）
    """
    print("\n=== Multiple Long Waits Test (60s each) ===")
    
    tester = LongIdleConnectionTester()
    limits = httpx.Limits(max_keepalive_connections=5, keepalive_expiry=120)
    
    async with httpx.AsyncClient(limits=limits, http2=True) as client:
        base_url = "https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries"
        
        for cycle in range(3):
            print(f"\n--- Cycle {cycle + 1} ---")
            
            # リクエスト実行
            await tester.test_request_with_timing(
                client,
                f"{base_url}?start={cycle * 2}&end={cycle * 2}",
                f"Cycle {cycle + 1} - First"
            )
            
            # 60秒待機
            if cycle < 2:  # 最後のサイクルでは待機しない
                print(f"Waiting 60 seconds...")
                await asyncio.sleep(60)
    
    print(f"\n--- Multiple waits analysis ---")
    times = [req['response_time'] for req in tester.connection_history if req.get('success')]
    for i, t in enumerate(times):
        status = "initial" if i == 0 else f"after 60s wait #{i}"
        print(f"Request {i+1} ({status}): {t:.3f}s")

async def main():
    """
    メイン関数
    """
    print("HTTPX HTTP/2 Long Idle Connection Test")
    print("="*80)
    print("Testing connection persistence after 180 seconds of inactivity")
    print("This test will take approximately 4 minutes to complete...")
    
    try:
        # メインテスト（180秒待機）
        await test_long_idle_connection()
        
        # 追加テスト（60秒待機 x 3回）
        # await test_multiple_long_waits()
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        logger.exception("Test failed")
    
    print("\n" + "="*80)
    print("【テスト完了】")
    print("長時間待機後の接続動作を検証しました")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
