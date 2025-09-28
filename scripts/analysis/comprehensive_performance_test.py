"""
包括的性能比較テスト
7つのパターンを比較して最終的なテーブル結果を出力
"""
import requests
import aiohttp
import httpx
import asyncio
import time
from typing import List, Dict, Any

class ComprehensivePerformanceTester:
    def __init__(self):
        self.results = {}
        self.base_url = "https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries"
        
    def measure_time(self, func):
        """デコレータ：実行時間を測定"""
        def wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            end = time.time()
            return result, end - start
        return wrapper
    
    async def measure_time_async(self, func):
        """非同期関数の実行時間を測定"""
        start = time.time()
        result = await func()
        end = time.time()
        return result, end - start
    
    # 1.1. requests / HTTP/1.1 (no keep-alive)
    def test_requests_http11_no_keepalive(self):
        """requests HTTP/1.1 keep-aliveなし"""
        print("\n🧪 1.1. requests / HTTP/1.1 (no keep-alive)")
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            # 新しいセッションで毎回リクエスト（keep-aliveなし）
            resp = requests.get(url, headers={'Connection': 'close'})
            end = time.time()
            response_time = end - start
            times.append(response_time)
            print(f"  Request {i+1}: {response_time:.3f}s (Status: {resp.status_code})")
            time.sleep(0.1)
        
        return times
    
    # 1.2. requests / HTTP/1.1 + keep-alive
    def test_requests_http11_keepalive(self):
        """requests HTTP/1.1 keep-alive有効"""
        print("\n🧪 1.2. requests / HTTP/1.1 + keep-alive")
        times = []
        
        session = requests.Session()
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            resp = session.get(url)
            end = time.time()
            response_time = end - start
            times.append(response_time)
            print(f"  Request {i+1}: {response_time:.3f}s (Status: {resp.status_code})")
            time.sleep(0.1)
        
        session.close()
        return times
    
    # 2.1. aiohttp / HTTP/1.1 (default)
    async def test_aiohttp_http11_default(self):
        """aiohttp HTTP/1.1 デフォルト"""
        print("\n🧪 2.1. aiohttp / HTTP/1.1")
        times = []
        
        async with aiohttp.ClientSession() as session:
            for i in range(3):
                url = f"{self.base_url}?start={i}&end={i}"
                start = time.time()
                async with session.get(url) as resp:
                    await resp.text()
                    end = time.time()
                    response_time = end - start
                    times.append(response_time)
                    print(f"  Request {i+1}: {response_time:.3f}s (Status: {resp.status})")
                await asyncio.sleep(0.1)
        
        return times
    
    # 2.2. aiohttp / HTTP/1.1 + keep-alive (明示的設定)
    async def test_aiohttp_http11_keepalive(self):
        """aiohttp HTTP/1.1 keep-alive明示的設定"""
        print("\n🧪 2.2. aiohttp / HTTP/1.1 + keep-alive")
        times = []
        
        connector = aiohttp.TCPConnector(
            limit=10,
            limit_per_host=5,
            keepalive_timeout=60,
            enable_cleanup_closed=True
        )
        
        async with aiohttp.ClientSession(connector=connector) as session:
            for i in range(3):
                url = f"{self.base_url}?start={i}&end={i}"
                start = time.time()
                async with session.get(url) as resp:
                    await resp.text()
                    end = time.time()
                    response_time = end - start
                    times.append(response_time)
                    print(f"  Request {i+1}: {response_time:.3f}s (Status: {resp.status})")
                await asyncio.sleep(0.1)
        
        return times
    
    # 3.1. httpx / HTTP/1.1
    async def test_httpx_http11(self):
        """httpx HTTP/1.1"""
        print("\n🧪 3.1. httpx / HTTP/1.1")
        times = []
        
        async with httpx.AsyncClient(http2=False) as client:
            for i in range(3):
                url = f"{self.base_url}?start={i}&end={i}"
                start = time.time()
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"  Request {i+1}: {response_time:.3f}s (Status: {resp.status_code}, Version: {resp.http_version})")
                await asyncio.sleep(0.1)
        
        return times
    
    # 3.2. httpx / HTTP/1.1 + keep-alive
    async def test_httpx_http11_keepalive(self):
        """httpx HTTP/1.1 keep-alive明示的設定"""
        print("\n🧪 3.2. httpx / HTTP/1.1 + keep-alive")
        times = []
        
        limits = httpx.Limits(
            max_keepalive_connections=10,
            max_connections=20,
            keepalive_expiry=60
        )
        
        async with httpx.AsyncClient(http2=False, limits=limits) as client:
            for i in range(3):
                url = f"{self.base_url}?start={i}&end={i}"
                start = time.time()
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"  Request {i+1}: {response_time:.3f}s (Status: {resp.status_code}, Version: {resp.http_version})")
                await asyncio.sleep(0.1)
        
        return times
    
    # 4.1. httpx / HTTP/2 (自動keep-alive)
    async def test_httpx_http2(self):
        """httpx HTTP/2 (自動keep-alive)"""
        print("\n🧪 4.1. httpx / HTTP/2 (auto keep-alive)")
        times = []
        
        async with httpx.AsyncClient(http2=True) as client:
            for i in range(3):
                url = f"{self.base_url}?start={i}&end={i}"
                start = time.time()
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"  Request {i+1}: {response_time:.3f}s (Status: {resp.status_code}, Version: {resp.http_version})")
                await asyncio.sleep(0.1)
        
        return times
    
    async def run_all_tests(self):
        """全テストを実行"""
        print("=" * 80)
        print("包括的性能比較テスト")
        print("各パターンで3回のリクエストを実行し、response timeを測定")
        print("=" * 80)
        
        # 1.1. requests HTTP/1.1 (no keep-alive)
        try:
            times_1_1 = self.test_requests_http11_no_keepalive()
            self.results['1.1_requests_http11_no_keepalive'] = times_1_1
        except Exception as e:
            print(f"  ❌ Error: {e}")
            self.results['1.1_requests_http11_no_keepalive'] = [0, 0, 0]
        
        # 1.2. requests HTTP/1.1 + keep-alive
        try:
            times_1_2 = self.test_requests_http11_keepalive()
            self.results['1.2_requests_http11_keepalive'] = times_1_2
        except Exception as e:
            print(f"  ❌ Error: {e}")
            self.results['1.2_requests_http11_keepalive'] = [0, 0, 0]
        
        # 2.1. aiohttp HTTP/1.1
        try:
            times_2_1 = await self.test_aiohttp_http11_default()
            self.results['2.1_aiohttp_http11'] = times_2_1
        except Exception as e:
            print(f"  ❌ Error: {e}")
            self.results['2.1_aiohttp_http11'] = [0, 0, 0]
        
        # 2.2. aiohttp HTTP/1.1 + keep-alive
        try:
            times_2_2 = await self.test_aiohttp_http11_keepalive()
            self.results['2.2_aiohttp_http11_keepalive'] = times_2_2
        except Exception as e:
            print(f"  ❌ Error: {e}")
            self.results['2.2_aiohttp_http11_keepalive'] = [0, 0, 0]
        
        # 3.1. httpx HTTP/1.1
        try:
            times_3_1 = await self.test_httpx_http11()
            self.results['3.1_httpx_http11'] = times_3_1
        except Exception as e:
            print(f"  ❌ Error: {e}")
            self.results['3.1_httpx_http11'] = [0, 0, 0]
        
        # 3.2. httpx HTTP/1.1 + keep-alive
        try:
            times_3_2 = await self.test_httpx_http11_keepalive()
            self.results['3.2_httpx_http11_keepalive'] = times_3_2
        except Exception as e:
            print(f"  ❌ Error: {e}")
            self.results['3.2_httpx_http11_keepalive'] = [0, 0, 0]
        
        # 4.1. httpx HTTP/2
        try:
            times_4_1 = await self.test_httpx_http2()
            self.results['4.1_httpx_http2'] = times_4_1
        except Exception as e:
            print(f"  ❌ Error: {e}")
            self.results['4.1_httpx_http2'] = [0, 0, 0]
        
        # 結果テーブルの表示
        self.display_results_table()
    
    def display_results_table(self):
        """結果をテーブル形式で表示"""
        print("\n" + "=" * 100)
        print("【最終結果テーブル】")
        print("=" * 100)
        
        # ヘッダー
        header = f"{'Pattern':<35} {'Request 1':<12} {'Request 2':<12} {'Request 3':<12} {'Average':<12} {'Improvement'}"
        print(header)
        print("-" * 100)
        
        # 基準値（requests no keep-alive）の平均を取得
        baseline_avg = sum(self.results.get('1.1_requests_http11_no_keepalive', [0, 0, 0])) / 3 if self.results.get('1.1_requests_http11_no_keepalive') else 1
        
        patterns = [
            ('1.1_requests_http11_no_keepalive', '1.1 requests/HTTP1.1 (no keep-alive)'),
            ('1.2_requests_http11_keepalive', '1.2 requests/HTTP1.1 + keep-alive'),
            ('2.1_aiohttp_http11', '2.1 aiohttp/HTTP1.1'),
            ('2.2_aiohttp_http11_keepalive', '2.2 aiohttp/HTTP1.1 + keep-alive'),
            ('3.1_httpx_http11', '3.1 httpx/HTTP1.1'),
            ('3.2_httpx_http11_keepalive', '3.2 httpx/HTTP1.1 + keep-alive'),
            ('4.1_httpx_http2', '4.1 httpx/HTTP2 (auto keep-alive)')
        ]
        
        for key, description in patterns:
            times = self.results.get(key, [0, 0, 0])
            avg = sum(times) / 3 if times else 0
            
            # 改善率計算
            if baseline_avg > 0 and avg > 0:
                improvement = ((baseline_avg - avg) / baseline_avg) * 100
                improvement_str = f"{improvement:+.1f}%"
            else:
                improvement_str = "N/A"
            
            row = f"{description:<35} {times[0]:<12.3f} {times[1]:<12.3f} {times[2]:<12.3f} {avg:<12.3f} {improvement_str}"
            print(row)
        
        print("-" * 100)
        
        # 最速パターンの特定
        best_pattern = None
        best_avg = float('inf')
        for key, description in patterns:
            times = self.results.get(key, [0, 0, 0])
            avg = sum(times) / 3 if times else float('inf')
            if avg < best_avg and avg > 0:
                best_avg = avg
                best_pattern = description
        
        if best_pattern:
            print(f"\n🏆 最高性能: {best_pattern} (平均 {best_avg:.3f}s)")
        
        # 分析コメント
        print(f"\n【分析】")
        print(f"• ベースライン (requests no keep-alive): {baseline_avg:.3f}s")
        print(f"• keep-aliveの効果が明確に現れるパターンを確認")
        print(f"• HTTP/2の自動多重化による最適化効果を検証")
        print(f"• query parameterが変わる場合の各ライブラリの対応を比較")

async def main():
    """メイン関数"""
    tester = ComprehensivePerformanceTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
