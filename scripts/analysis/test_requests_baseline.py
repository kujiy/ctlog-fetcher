"""
requestsでHTTP/1.1 keep-aliveなしのベースライン測定
httpx + HTTP/2と比較するための基準値を取得
"""
import requests
import time
import json

class RequestsBaselineTester:
    def __init__(self):
        self.results = []
        self.request_count = 0
    
    def test_request(self, url, label=""):
        """
        requestsでのシンプルなリクエストテスト
        """
        self.request_count += 1
        req_id = self.request_count
        
        print(f"\n--- Request {req_id} {label} ---")
        print(f"Time: {time.strftime('%H:%M:%S')}")
        print(f"URL: {url}")
        
        start_time = time.time()
        try:
            # keep-aliveを無効化した新しいセッションで毎回リクエスト
            session = requests.Session()
            session.headers.update({'Connection': 'close'})
            
            resp = requests.get(url)
            end_time = time.time()
            
            # レスポンス情報
            print(f"Status: {resp.status_code}")
            print(f"Response time: {end_time - start_time:.3f}s")
            print(f"HTTP Version: HTTP/1.1")  # requestsは常にHTTP/1.1
            
            # ヘッダー確認
            connection_header = resp.headers.get('connection', 'N/A')
            print(f"Connection header: {connection_header}")
            
            # レスポンス内容の確認
            response_length = len(resp.text)
            print(f"Response length: {response_length} chars")
            
            # JSON解析
            entries_count = 0
            try:
                response_data = resp.json()
                if 'entries' in response_data:
                    entries_count = len(response_data['entries'])
                    print(f"CT Log entries: {entries_count}")
            except:
                pass
            
            result = {
                'request_id': req_id,
                'timestamp': time.time(),
                'url': url,
                'status': resp.status_code,
                'response_time': end_time - start_time,
                'http_version': 'HTTP/1.1',
                'content_length': response_length,
                'entries_count': entries_count,
                'connection_header': connection_header,
                'success': True
            }
            
            self.results.append(result)
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
            
            self.results.append(result)
            return result

def test_requests_baseline():
    """
    requestsでのベースライン測定
    """
    print("=== Requests HTTP/1.1 Baseline Test ===")
    print("Testing requests library with no keep-alive (Connection: close)")
    
    tester = RequestsBaselineTester()
    base_url = "https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries"
    
    # 連続リクエストテスト（keep-aliveなし）
    print("\n🔵 連続リクエスト（毎回新規接続）")
    
    for i in range(10):
        url = f"{base_url}?start={i}&end={i}"
        tester.test_request(url, f"No keep-alive #{i+1}")
        time.sleep(0.5)  # 0.5秒間隔
    
    # 結果の分析
    analyze_baseline_results(tester.results)
    
    return tester.results

def analyze_baseline_results(results):
    """
    ベースライン結果の分析
    """
    print("\n" + "="*70)
    print("【Requests HTTP/1.1 Baseline 結果分析】")
    print("="*70)
    
    successful_requests = [req for req in results if req.get('success', False)]
    failed_requests = [req for req in results if not req.get('success', False)]
    
    print(f"Total requests: {len(results)}")
    print(f"Successful requests: {len(successful_requests)}")
    print(f"Failed requests: {len(failed_requests)}")
    
    if successful_requests:
        response_times = [req['response_time'] for req in successful_requests]
        
        # 統計情報
        avg_time = sum(response_times) / len(response_times)
        min_time = min(response_times)
        max_time = max(response_times)
        
        print(f"\n--- レスポンス時間統計 ---")
        print(f"平均レスポンス時間: {avg_time:.3f}s")
        print(f"最短レスポンス時間: {min_time:.3f}s")
        print(f"最長レスポンス時間: {max_time:.3f}s")
        print(f"標準偏差: {calculate_std_dev(response_times, avg_time):.3f}s")
        
        # 個別のレスポンス時間
        print(f"\n--- 個別レスポンス時間 ---")
        for i, req in enumerate(successful_requests):
            print(f"Request {i+1}: {req['response_time']:.3f}s")
        
        # 接続ヘッダーの確認
        connection_headers = [req.get('connection_header', 'N/A') for req in successful_requests]
        unique_headers = set(connection_headers)
        print(f"\n--- 接続ヘッダー ---")
        for header in unique_headers:
            count = connection_headers.count(header)
            print(f"{header}: {count} requests")

def calculate_std_dev(values, mean):
    """
    標準偏差を計算
    """
    if len(values) <= 1:
        return 0.0
    
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return variance ** 0.5

def compare_with_httpx_results():
    """
    httpxの結果と比較（概算値を使用）
    """
    print(f"\n{'='*70}")
    print(f"【httpx HTTP/2 との比較】")
    print(f"{'='*70}")
    
    # httpxの結果（前回のテストから）
    httpx_initial = 0.133  # 初回リクエスト
    httpx_subsequent = 0.010  # 接続再利用時
    
    print(f"httpx HTTP/2:")
    print(f"  初回リクエスト: {httpx_initial:.3f}s")
    print(f"  接続再利用時: {httpx_subsequent:.3f}s")
    print(f"  効率化: {((httpx_initial - httpx_subsequent) / httpx_initial * 100):.1f}%")
    
    print(f"\nrequests HTTP/1.1 (no keep-alive):")
    print(f"  全リクエスト: 上記統計参照")
    print(f"  接続再利用: なし（毎回新規接続）")

def main():
    """
    メイン関数
    """
    print("Requests HTTP/1.1 Baseline Measurement")
    print("="*70)
    print("Measuring baseline performance with requests library")
    print("Connection: close (no keep-alive)")
    
    try:
        test_requests_baseline()
        compare_with_httpx_results()
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
    
    print("\n" + "="*70)
    print("【ベースライン測定完了】")
    print("requests HTTP/1.1 (no keep-alive) のベースライン性能を測定しました")
    print("="*70)

if __name__ == "__main__":
    main()
