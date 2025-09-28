"""
HTTPライブラリの各種接続パターンの性能比較テスト
requests, aiohttp, httpx それぞれで以下のパターンを比較:
- HTTP/1.1 デフォルト
- HTTP/1.1 + Connection: close
- HTTP/1.1 + Keep-Alive ヘッダー
- HTTP/1.1 + Session/再利用
"""
import requests
import aiohttp
import httpx
import asyncio
import time
import sys
import argparse
from typing import List, Dict, Tuple

class HTTPConnectionPerformanceTester:
    def __init__(self):
        self.base_url = "https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries"
        self.warm_up_url = f"{self.base_url}?start=0&end=0"
    
    def warm_up(self):
        """DNS cache等のwarm up"""
        print("🔥 Warming up (DNS cache, SSL handshake)...", file=sys.stderr)
        try:
            resp = requests.get(self.warm_up_url, timeout=10)
            print(f"   Warm up completed: {resp.status_code}", file=sys.stderr)
        except Exception as e:
            print(f"   Warm up failed: {e}", file=sys.stderr)
        time.sleep(1)
    
    # ========== requests tests ==========
    def test_requests_default(self) -> List[float]:
        """1.1. requests / HTTP1.1 (default)"""
        print("\n📊 1.1. requests / HTTP1.1 (default)", file=sys.stderr)
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            resp = requests.get(url)
            end = time.time()
            response_time = end - start
            times.append(response_time)
            print(f"   Request {i+1}: {response_time:.3f}s", file=sys.stderr)
            time.sleep(0.5)
        
        return times
    
    def test_requests_connection_close(self) -> List[float]:
        """1.2. requests / HTTP1.1 + Connection: close"""
        print("\n📊 1.2. requests / HTTP1.1 + Connection: close", file=sys.stderr)
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            resp = requests.get(url, headers={'Connection': 'close'})
            end = time.time()
            response_time = end - start
            times.append(response_time)
            print(f"   Request {i+1}: {response_time:.3f}s", file=sys.stderr)
            time.sleep(0.5)
        
        return times
    
    def test_requests_keep_alive_header(self) -> List[float]:
        """1.3. requests / HTTP1.1 + Keep-Alive header"""
        print("\n📊 1.3. requests / HTTP1.1 + Keep-Alive header", file=sys.stderr)
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            resp = requests.get(url, headers={'Connection': 'keep-alive'})
            end = time.time()
            response_time = end - start
            times.append(response_time)
            print(f"   Request {i+1}: {response_time:.3f}s", file=sys.stderr)
            time.sleep(0.5)
        
        return times
    
    def test_requests_session(self) -> List[float]:
        """1.4. requests / HTTP1.1 + Session (connection reuse)"""
        print("\n📊 1.4. requests / HTTP1.1 + Session (connection reuse)", file=sys.stderr)
        times = []
        
        with requests.Session() as session:
            for i in range(3):
                url = f"{self.base_url}?start={i}&end={i}"
                start = time.time()
                resp = session.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s", file=sys.stderr)
                time.sleep(0.5)
        
        return times
    
    # ========== aiohttp tests ==========
    async def test_aiohttp_default(self) -> List[float]:
        """2.1. aiohttp / HTTP1.1 (default)"""
        print("\n📊 2.1. aiohttp / HTTP1.1 (default)", file=sys.stderr)
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    await resp.text()
                    end = time.time()
                    response_time = end - start
                    times.append(response_time)
                    print(f"   Request {i+1}: {response_time:.3f}s", file=sys.stderr)
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_aiohttp_connection_close(self) -> List[float]:
        """2.2. aiohttp / HTTP1.1 + Connection: close"""
        print("\n📊 2.2. aiohttp / HTTP1.1 + Connection: close", file=sys.stderr)
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            async with aiohttp.ClientSession(
                headers={'Connection': 'close'},
                connector=aiohttp.TCPConnector(force_close=True)
            ) as session:
                async with session.get(url) as resp:
                    await resp.text()
                    end = time.time()
                    response_time = end - start
                    times.append(response_time)
                    print(f"   Request {i+1}: {response_time:.3f}s", file=sys.stderr)
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_aiohttp_keep_alive_header(self) -> List[float]:
        """2.3. aiohttp / HTTP1.1 + Keep-Alive header"""
        print("\n📊 2.3. aiohttp / HTTP1.1 + Keep-Alive header", file=sys.stderr)
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            async with aiohttp.ClientSession(
                headers={'Connection': 'keep-alive'}
            ) as session:
                async with session.get(url) as resp:
                    await resp.text()
                    end = time.time()
                    response_time = end - start
                    times.append(response_time)
                    print(f"   Request {i+1}: {response_time:.3f}s", file=sys.stderr)
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_aiohttp_session_reuse(self) -> List[float]:
        """2.4. aiohttp / HTTP1.1 + Session reuse"""
        print("\n📊 2.4. aiohttp / HTTP1.1 + Session reuse", file=sys.stderr)
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
                    print(f"   Request {i+1}: {response_time:.3f}s", file=sys.stderr)
                await asyncio.sleep(0.5)
        
        return times
    
    # ========== httpx tests ==========
    async def test_httpx_default(self) -> List[float]:
        """3.1. httpx / HTTP1.1 (default)"""
        print("\n📊 3.1. httpx / HTTP1.1 (default)", file=sys.stderr)
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            async with httpx.AsyncClient(http2=False) as client:
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s", file=sys.stderr)
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_httpx_connection_close(self) -> List[float]:
        """3.2. httpx / HTTP1.1 + Connection: close"""
        print("\n📊 3.2. httpx / HTTP1.1 + Connection: close", file=sys.stderr)
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            async with httpx.AsyncClient(
                http2=False,
                headers={'Connection': 'close'},
                limits=httpx.Limits(max_keepalive_connections=0)
            ) as client:
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s", file=sys.stderr)
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_httpx_keep_alive_header(self) -> List[float]:
        """3.3. httpx / HTTP1.1 + Keep-Alive header"""
        print("\n📊 3.3. httpx / HTTP1.1 + Keep-Alive header", file=sys.stderr)
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            async with httpx.AsyncClient(
                http2=False,
                headers={'Connection': 'keep-alive'}
            ) as client:
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s", file=sys.stderr)
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_httpx_session_reuse(self) -> List[float]:
        """3.4. httpx / HTTP1.1 + Client reuse"""
        print("\n📊 3.4. httpx / HTTP1.1 + Client reuse", file=sys.stderr)
        times = []
        
        async with httpx.AsyncClient(http2=False) as client:
            for i in range(3):
                url = f"{self.base_url}?start={i}&end={i}"
                start = time.time()
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s", file=sys.stderr)
                await asyncio.sleep(0.5)
        
        return times
    
    # ========== httpx HTTP/2 tests ==========
    async def test_httpx_http2_default(self) -> List[float]:
        """4.1. httpx / HTTP2 (default)"""
        print("\n📊 4.1. httpx / HTTP2 (default)", file=sys.stderr)
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            async with httpx.AsyncClient(http2=True) as client:
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s (HTTP/{resp.http_version})", file=sys.stderr)
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_httpx_http2_connection_close(self) -> List[float]:
        """4.2. httpx / HTTP2 + Connection: close"""
        print("\n📊 4.2. httpx / HTTP2 + Connection: close", file=sys.stderr)
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            async with httpx.AsyncClient(
                http2=True,
                headers={'Connection': 'close'},
                limits=httpx.Limits(max_keepalive_connections=0)
            ) as client:
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s (HTTP/{resp.http_version})", file=sys.stderr)
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_httpx_http2_keep_alive_header(self) -> List[float]:
        """4.3. httpx / HTTP2 + Keep-Alive header"""
        print("\n📊 4.3. httpx / HTTP2 + Keep-Alive header", file=sys.stderr)
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            async with httpx.AsyncClient(
                http2=True,
                headers={'Connection': 'keep-alive'}
            ) as client:
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s (HTTP/{resp.http_version})", file=sys.stderr)
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_httpx_http2_session_reuse(self) -> List[float]:
        """4.4. httpx / HTTP2 + Client reuse"""
        print("\n📊 4.4. httpx / HTTP2 + Client reuse", file=sys.stderr)
        times = []
        
        async with httpx.AsyncClient(http2=True) as client:
            for i in range(3):
                url = f"{self.base_url}?start={i}&end={i}"
                start = time.time()
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s (HTTP/{resp.http_version})", file=sys.stderr)
                await asyncio.sleep(0.5)
        
        return times
    
    # ========== Single test execution ==========
    async def run_single_test(self, test_id: str) -> List[float]:
        """単一テストを実行"""
        # Warm up (各テストで1回だけ実行)
        self.warm_up()
        
        test_mapping = {
            '1.1': self.test_requests_default,
            '1.2': self.test_requests_connection_close,
            '1.3': self.test_requests_keep_alive_header,
            '1.4': self.test_requests_session,
            '2.1': self.test_aiohttp_default,
            '2.2': self.test_aiohttp_connection_close,
            '2.3': self.test_aiohttp_keep_alive_header,
            '2.4': self.test_aiohttp_session_reuse,
            '3.1': self.test_httpx_default,
            '3.2': self.test_httpx_connection_close,
            '3.3': self.test_httpx_keep_alive_header,
            '3.4': self.test_httpx_session_reuse,
            '4.1': self.test_httpx_http2_default,
            '4.2': self.test_httpx_http2_connection_close,
            '4.3': self.test_httpx_http2_keep_alive_header,
            '4.4': self.test_httpx_http2_session_reuse,
        }
        
        if test_id not in test_mapping:
            raise ValueError(f"Invalid test ID: {test_id}. Valid IDs: {list(test_mapping.keys())}")
        
        test_func = test_mapping[test_id]
        
        # aiohttpとhttpxのテストは非同期
        if test_id.startswith('2.') or test_id.startswith('3.') or test_id.startswith('4.'):
            return await test_func()
        else:
            return test_func()
    
    def format_single_result(self, test_id: str, times: List[float]) -> str:
        """単一テスト結果をフォーマット"""
        pattern_descriptions = {
            '1.1': '1.1 requests/HTTP1.1 (default)',
            '1.2': '1.2 requests/HTTP1.1 + close',
            '1.3': '1.3 requests/HTTP1.1 + keep-alive',
            '1.4': '1.4 requests/HTTP1.1 + Session',
            '2.1': '2.1 aiohttp/HTTP1.1 (default)',
            '2.2': '2.2 aiohttp/HTTP1.1 + close',
            '2.3': '2.3 aiohttp/HTTP1.1 + keep-alive',
            '2.4': '2.4 aiohttp/HTTP1.1 + Session',
            '3.1': '3.1 httpx/HTTP1.1 (default)',
            '3.2': '3.2 httpx/HTTP1.1 + close',
            '3.3': '3.3 httpx/HTTP1.1 + keep-alive',
            '3.4': '3.4 httpx/HTTP1.1 + Client reuse',
            '4.1': '4.1 httpx/HTTP2 (default)',
            '4.2': '4.2 httpx/HTTP2 + close',
            '4.3': '4.3 httpx/HTTP2 + keep-alive',
            '4.4': '4.4 httpx/HTTP2 + Client reuse',
        }
        
        avg = sum(times) / len(times)
        description = pattern_descriptions.get(test_id, test_id)
        
        # Average の Req1 に対する割合を計算
        percentage = (avg / times[0]) * 100 if times[0] > 0 else 0
        
        # 性能改善の分析
        if len(times) >= 3:
            first_time = times[0]
            subsequent_avg = sum(times[1:]) / len(times[1:])
            improvement = (first_time - subsequent_avg) / first_time * 100 if first_time > 0 else 0
            
            # subsequent_avg が first_time の 0.5倍以下ならstrong improvement
            if subsequent_avg <= first_time * 0.5:
                analysis = "🚀 Strong improvement"
            elif improvement > 10:
                analysis = "✅ Good improvement"
            elif improvement > 5:
                analysis = "⚠️ Slight improvement"
            else:
                analysis = "➖ Consistent performance"  
        else:
            analysis = "📊 N/A"
        
        return f"{description:<35} {times[0]:<10.3f} {times[1]:<10.3f} {times[2]:<10.3f} {avg:<12.3f} {percentage:<8.1f}% {analysis}"

    async def run_all_tests(self) -> Dict[str, List[float]]:
        """全テストを実行"""
        print("HTTP Connection Performance Comparison Test")
        print("=" * 80)
        
        # Warm up
        self.warm_up()
        
        results = {}
        
        # requests tests
        print("\n🔹 REQUESTS TESTS")
        print("-" * 40)
        results['1.1_requests_default'] = self.test_requests_default()
        time.sleep(2)
        results['1.2_requests_close'] = self.test_requests_connection_close()
        time.sleep(2)
        results['1.3_requests_keepalive'] = self.test_requests_keep_alive_header()
        time.sleep(2)
        results['1.4_requests_session'] = self.test_requests_session()
        time.sleep(2)
        
        # aiohttp tests
        print("\n🔹 AIOHTTP TESTS")
        print("-" * 40)
        results['2.1_aiohttp_default'] = await self.test_aiohttp_default()
        await asyncio.sleep(2)
        results['2.2_aiohttp_close'] = await self.test_aiohttp_connection_close()
        await asyncio.sleep(2)
        results['2.3_aiohttp_keepalive'] = await self.test_aiohttp_keep_alive_header()
        await asyncio.sleep(2)
        results['2.4_aiohttp_session'] = await self.test_aiohttp_session_reuse()
        await asyncio.sleep(2)
        
        # httpx tests
        print("\n🔹 HTTPX TESTS")
        print("-" * 40)
        results['3.1_httpx_default'] = await self.test_httpx_default()
        await asyncio.sleep(2)
        results['3.2_httpx_close'] = await self.test_httpx_connection_close()
        await asyncio.sleep(2)
        results['3.3_httpx_keepalive'] = await self.test_httpx_keep_alive_header()
        await asyncio.sleep(2)
        results['3.4_httpx_session'] = await self.test_httpx_session_reuse()
        await asyncio.sleep(2)
        
        # httpx HTTP/2 tests
        print("\n🔹 HTTPX HTTP/2 TESTS")
        print("-" * 40)
        results['4.1_httpx_http2_default'] = await self.test_httpx_http2_default()
        await asyncio.sleep(2)
        results['4.2_httpx_http2_close'] = await self.test_httpx_http2_connection_close()
        await asyncio.sleep(2)
        results['4.3_httpx_http2_keepalive'] = await self.test_httpx_http2_keep_alive_header()
        await asyncio.sleep(2)
        results['4.4_httpx_http2_session'] = await self.test_httpx_http2_session_reuse()
        
        return results
    
    def display_results_table(self, results: Dict[str, List[float]]):
        """結果をテーブル形式で表示"""
        print("\n" + "=" * 110)
        print("📋 HTTP CONNECTION PERFORMANCE RESULTS")
        print("=" * 110)
        
        # ヘッダー
        print(f"{'Pattern':<35} {'Req1 (s)':<10} {'Req2 (s)':<10} {'Req3 (s)':<10} {'Average (s)':<12} {'Avg/Req1':<9} {'Analysis'}")
        print("-" * 110)
        
        # パターンの説明
        pattern_descriptions = {
            '1.1_requests_default': '1.1 requests/HTTP1.1 (default)',
            '1.2_requests_close': '1.2 requests/HTTP1.1 + close',
            '1.3_requests_keepalive': '1.3 requests/HTTP1.1 + keep-alive',
            '1.4_requests_session': '1.4 requests/HTTP1.1 + Session',
            '2.1_aiohttp_default': '2.1 aiohttp/HTTP1.1 (default)',
            '2.2_aiohttp_close': '2.2 aiohttp/HTTP1.1 + close',
            '2.3_aiohttp_keepalive': '2.3 aiohttp/HTTP1.1 + keep-alive',
            '2.4_aiohttp_session': '2.4 aiohttp/HTTP1.1 + Session',
            '3.1_httpx_default': '3.1 httpx/HTTP1.1 (default)',
            '3.2_httpx_close': '3.2 httpx/HTTP1.1 + close',
            '3.3_httpx_keepalive': '3.3 httpx/HTTP1.1 + keep-alive',
            '3.4_httpx_session': '3.4 httpx/HTTP1.1 + Client reuse',
            '4.1_httpx_http2_default': '4.1 httpx/HTTP2 (default)',
            '4.2_httpx_http2_close': '4.2 httpx/HTTP2 + close',
            '4.3_httpx_http2_keepalive': '4.3 httpx/HTTP2 + keep-alive',
            '4.4_httpx_http2_session': '4.4 httpx/HTTP2 + Client reuse',
        }
        
        for key in sorted(results.keys()):
            times = results[key]
            avg = sum(times) / len(times)
            description = pattern_descriptions.get(key, key)
            
            # 性能改善の分析
            if len(times) >= 3:
                first_time = times[0]
                subsequent_avg = sum(times[1:]) / len(times[1:])
                improvement = (first_time - subsequent_avg) / first_time * 100 if first_time > 0 else 0
                
                if improvement > 100:
                    analysis = "🚀 Strong improvement"
                elif improvement > 10:
                    analysis = "✅ Good improvement"
                elif improvement > 5:
                    analysis = "⚠️ Slight improvement"
                else:
                    analysis = "➖ Consistent performance"
            else:
                analysis = "📊 N/A"
            
            # Average の Req1 に対する割合を計算
            percentage = (avg / times[0]) * 100 if times[0] > 0 else 0
            
            print(f"{description:<35} {times[0]:<10.3f} {times[1]:<10.3f} {times[2]:<10.3f} {avg:<12.3f} {percentage:<8.1f}% {analysis}")
        
        # 統計分析
        print("\n" + "=" * 110)
        print("📊 STATISTICAL ANALYSIS")
        print("=" * 110)
        
        # 各ライブラリのパフォーマンス比較
        self.analyze_by_library(results)
        
        # 接続パターン別の比較
        self.analyze_by_pattern(results)
    
    def analyze_by_library(self, results: Dict[str, List[float]]):
        """ライブラリ別の分析"""
        print("\n🔍 Performance by Library:")
        print("-" * 50)
        
        libraries = ['requests', 'aiohttp', 'httpx']
        for lib in libraries:
            lib_results = {k: v for k, v in results.items() if lib in k}
            
            if lib_results:
                all_times = []
                for times in lib_results.values():
                    all_times.extend(times)
                
                avg_time = sum(all_times) / len(all_times)
                min_time = min(all_times)
                max_time = max(all_times)
                
                print(f"{lib.upper():>10}: avg={avg_time:.3f}s, min={min_time:.3f}s, max={max_time:.3f}s")
    
    def analyze_by_pattern(self, results: Dict[str, List[float]]):
        """接続パターン別の分析"""
        print("\n🔍 Performance by Connection Pattern:")
        print("-" * 50)
        
        patterns = ['default', 'close', 'keepalive', 'session']
        for pattern in patterns:
            pattern_results = {k: v for k, v in results.items() if pattern in k}
            
            if pattern_results:
                all_times = []
                for times in pattern_results.values():
                    all_times.extend(times)
                
                avg_time = sum(all_times) / len(all_times)
                min_time = min(all_times)
                max_time = max(all_times)
                
                pattern_name = pattern.replace('session', 'Session/Client reuse').title()
                print(f"{pattern_name:>15}: avg={avg_time:.3f}s, min={min_time:.3f}s, max={max_time:.3f}s")

async def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description='HTTP Connection Performance Test')
    parser.add_argument('--test', type=str, help='Test to run (e.g., 1.1, 1.2, ..., 3.4)')
    parser.add_argument('--all', action='store_true', help='Run all tests')
    
    args = parser.parse_args()
    
    tester = HTTPConnectionPerformanceTester()
    
    if args.test:
        try:
            # 単一テスト実行
            times = await tester.run_single_test(args.test)
            result_line = tester.format_single_result(args.test, times)
            print(result_line)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.all:
        # 全テスト実行（従来通り）
        results = await tester.run_all_tests()
        tester.display_results_table(results)
    else:
        print("Usage: python test_http_performance.py --test <test_id> | --all")
        print("Available test IDs: 1.1-1.4 (requests), 2.1-2.4 (aiohttp), 3.1-3.4 (httpx/HTTP1.1), 4.1-4.4 (httpx/HTTP2)")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())