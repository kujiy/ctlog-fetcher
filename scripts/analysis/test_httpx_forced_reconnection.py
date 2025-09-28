"""
httpx + HTTP/2での強制的な再接続テスト
keepalive_expiryを短く設定して再接続動作を検証
"""
import httpx
import asyncio
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ForcedReconnectionTester:
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
            response = await client.get(url)
            end_time = time.time()
            
            print(f"Status: {response.status_code}")
            print(f"Response time: {end_time - start_time:.3f}s")
            print(f"HTTP Version: {response.http_version}")
            
            # レスポンス内容の確認
            response_text = response.text
            response_length = len(response_text)
            print(f"Response length: {response_length} chars")
            
            result = {
                'request_id': req_id,
                'timestamp': time.time(),
                'url': url,
                'status': response.status_code,
                'response_time': end_time - start_time,
                'http_version': response.http_version,
                'content_length': response_length,
                'success': True
            }
            
            self.connection_history.append(result)
            return result
                
        except Exception as e:
            end_time = time.time()
            print(f"❌ Request {req_id} failed: {e}")
            print(f"Error type: {type(e).__name__}")
            
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

async def test_forced_reconnection_scenarios():
    """
    異なるkeepalive_expiry設定での再接続テスト
    """
    print("=== Forced Reconnection Test ===")
    print("Testing different keepalive_expiry settings")
    
    scenarios = [
        {"expiry": 10, "wait": 15, "name": "Short expiry (10s, wait 15s)"},
        {"expiry": 30, "wait": 45, "name": "Medium expiry (30s, wait 45s)"},
        {"expiry": 5, "wait": 10, "name": "Very short expiry (5s, wait 10s)"}
    ]
    
    all_results = []
    
    for scenario in scenarios:
        print(f"\n{'='*60}")
        print(f"🧪 {scenario['name']}")
        print(f"{'='*60}")
        
        tester = ForcedReconnectionTester()
        
        # 接続設定
        limits = httpx.Limits(
            max_keepalive_connections=5, 
            max_connections=10,
            keepalive_expiry=scenario['expiry']  # 短いkeep-alive
        )
        timeout = httpx.Timeout(30.0)
        
        async with httpx.AsyncClient(
            limits=limits, 
            timeout=timeout,
            http2=True
        ) as client:
            
            base_url = "https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries"
            
            # 初期リクエスト
            print(f"\n🔵 初期リクエスト")
            await tester.test_request_with_timing(
                client, 
                f"{base_url}?start=0&end=0", 
                "Initial connection"
            )
            
            # 短時間待機後のリクエスト（接続維持確認）
            print(f"\n🔵 短時間待機後（3秒）")
            await asyncio.sleep(3)
            await tester.test_request_with_timing(
                client, 
                f"{base_url}?start=1&end=1", 
                "After 3s wait"
            )
            
            # keepalive_expiry後の待機
            wait_time = scenario['wait']
            print(f"\n🔵 keepalive expiry後の待機（{wait_time}秒）")
            print(f"Waiting {wait_time} seconds (expiry: {scenario['expiry']}s)...")
            
            # 待機を分割して進捗表示
            for i in range(wait_time // 5):
                await asyncio.sleep(5)
                remaining = wait_time - (i + 1) * 5
                if remaining > 0:
                    print(f"... {remaining} seconds remaining")
            
            # 残り時間
            remaining_time = wait_time % 5
            if remaining_time > 0:
                await asyncio.sleep(remaining_time)
            
            # expiry後のリクエスト（再接続期待）
            await tester.test_request_with_timing(
                client, 
                f"{base_url}?start=2&end=2", 
                f"After {wait_time}s wait (expiry+{wait_time-scenario['expiry']}s)"
            )
            
            # 再接続後の連続リクエスト
            print(f"\n🔵 再接続後の連続リクエスト")
            for i in range(2):
                await tester.test_request_with_timing(
                    client, 
                    f"{base_url}?start={i+3}&end={i+3}", 
                    f"Post-reconnection #{i+1}"
                )
                await asyncio.sleep(1)
        
        # シナリオ結果の分析
        analyze_scenario_results(tester.connection_history, scenario)
        all_results.append({
            'scenario': scenario,
            'results': tester.connection_history
        })
    
    # 全シナリオの比較分析
    compare_all_scenarios(all_results)
    
    return all_results

def analyze_scenario_results(history, scenario):
    """
    各シナリオの結果分析
    """
    print(f"\n--- {scenario['name']} 結果分析 ---")
    
    successful_requests = [req for req in history if req.get('success', False)]
    
    if len(successful_requests) >= 3:
        initial_time = successful_requests[0]['response_time']
        short_wait_time = successful_requests[1]['response_time']
        long_wait_time = successful_requests[2]['response_time']
        
        print(f"初期リクエスト: {initial_time:.3f}s")
        print(f"3秒後リクエスト: {short_wait_time:.3f}s")
        print(f"{scenario['wait']}秒後リクエスト: {long_wait_time:.3f}s")
        
        # 再接続判定
        if long_wait_time > initial_time * 1.5:
            print(f"🔄 再接続発生: レスポンス時間が{((long_wait_time - initial_time) / initial_time * 100):.1f}%増加")
        elif long_wait_time <= short_wait_time * 1.3:
            print(f"✅ 接続維持: レスポンス時間変化は軽微({((long_wait_time - short_wait_time) / short_wait_time * 100):.1f}%)")
        else:
            print(f"⚠️ 不明確: 中程度のレスポンス時間変化")
        
        # 再接続後の安定性
        if len(successful_requests) > 3:
            post_times = [req['response_time'] for req in successful_requests[3:]]
            avg_post_time = sum(post_times) / len(post_times)
            print(f"再接続後平均: {avg_post_time:.3f}s")
    
    # HTTP/2一貫性
    http2_count = len([req for req in successful_requests if req.get('http_version') == 'HTTP/2'])
    print(f"HTTP/2使用: {http2_count}/{len(successful_requests)}")

def compare_all_scenarios(all_results):
    """
    全シナリオの比較分析
    """
    print(f"\n{'='*80}")
    print(f"【全シナリオ比較分析】")
    print(f"{'='*80}")
    
    for result in all_results:
        scenario = result['scenario']
        history = result['results']
        successful = [req for req in history if req.get('success', False)]
        
        if len(successful) >= 3:
            initial_time = successful[0]['response_time']
            long_wait_time = successful[2]['response_time']
            reconnection_detected = long_wait_time > initial_time * 1.5
            
            print(f"\n{scenario['name']}:")
            print(f"  Keepalive expiry: {scenario['expiry']}s")
            print(f"  Wait time: {scenario['wait']}s")
            print(f"  Initial response: {initial_time:.3f}s")
            print(f"  After wait response: {long_wait_time:.3f}s")
            print(f"  Reconnection: {'🔄 YES' if reconnection_detected else '✅ NO'}")
    
    print(f"\n--- 結論 ---")
    print(f"keepalive_expiryを短く設定することで：")
    print(f"1. 強制的な再接続をテストできる")
    print(f"2. 再接続時のレスポンス時間増加を観測できる")
    print(f"3. httpxの自動再接続機能を検証できる")

async def main():
    """
    メイン関数
    """
    print("HTTPX HTTP/2 Forced Reconnection Test")
    print("="*80)
    print("Testing automatic reconnection with short keepalive_expiry")
    
    try:
        await test_forced_reconnection_scenarios()
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        logger.exception("Test failed")
    
    print("\n" + "="*80)
    print("【強制再接続テスト完了】")
    print("keepalive_expiryによる再接続制御を検証しました")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
