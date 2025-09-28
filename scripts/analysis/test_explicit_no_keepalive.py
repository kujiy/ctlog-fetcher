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
        print("🔥 Warming up (DNS cache, SSL handshake)...")
        try:
            resp = requests.get(self.warm_up_url, timeout=10)
            print(f"   Warm up completed: {resp.status_code}")
        except Exception as e:
            print(f"   Warm up failed: {e}")
        time.sleep(1)
    
    # ========== requests tests ==========
    def test_requests_default(self) -> List[float]:
        """1.1. requests / HTTP1.1 (default)"""
        print("\n📊 1.1. requests / HTTP1.1 (default)")
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            resp = requests.get(url)
            end = time.time()
            response_time = end - start
            times.append(response_time)
            print(f"   Request {i+1}: {response_time:.3f}s")
            time.sleep(0.5)
        
        return times
    
    def test_requests_connection_close(self) -> List[float]:
        """1.2. requests / HTTP1.1 + Connection: close"""
        print("\n📊 1.2. requests / HTTP1.1 + Connection: close")
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            resp = requests.get(url, headers={'Connection': 'close'})
            end = time.time()
            response_time = end - start
            times.append(response_time)
            print(f"   Request {i+1}: {response_time:.3f}s")
            time.sleep(0.5)
        
        return times
    
    def test_requests_keep_alive_header(self) -> List[float]:
        """1.3. requests / HTTP1.1 + Keep-Alive header"""
        print("\n📊 1.3. requests / HTTP1.1 + Keep-Alive header")
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            resp = requests.get(url, headers={'Connection': 'keep-alive'})
            end = time.time()
            response_time = end - start
            times.append(response_time)
            print(f"   Request {i+1}: {response_time:.3f}s")
            time.sleep(0.5)
        
        return times
    
    def test_requests_session(self) -> List[float]:
        """1.4. requests / HTTP1.1 + Session (connection reuse)"""
        print("\n📊 1.4. requests / HTTP1.1 + Session (connection reuse)")
        times = []
        
        with requests.Session() as session:
            for i in range(3):
                url = f"{self.base_url}?start={i}&end={i}"
                start = time.time()
                resp = session.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s")
                time.sleep(0.5)
        
        return times
    
    # ========== aiohttp tests ==========
    async def test_aiohttp_default(self) -> List[float]:
        """2.1. aiohttp / HTTP1.1 (default)"""
        print("\n📊 2.1. aiohttp / HTTP1.1 (default)")
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
                    print(f"   Request {i+1}: {response_time:.3f}s")
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_aiohttp_connection_close(self) -> List[float]:
        """2.2. aiohttp / HTTP1.1 + Connection: close"""
        print("\n📊 2.2. aiohttp / HTTP1.1 + Connection: close")
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
                    print(f"   Request {i+1}: {response_time:.3f}s")
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_aiohttp_keep_alive_header(self) -> List[float]:
        """2.3. aiohttp / HTTP1.1 + Keep-Alive header"""
        print("\n📊 2.3. aiohttp / HTTP1.1 + Keep-Alive header")
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
                    print(f"   Request {i+1}: {response_time:.3f}s")
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_aiohttp_session_reuse(self) -> List[float]:
        """2.4. aiohttp / HTTP1.1 + Session reuse"""
        print("\n📊 2.4. aiohttp / HTTP1.1 + Session reuse")
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
                    print(f"   Request {i+1}: {response_time:.3f}s")
                await asyncio.sleep(0.5)
        
        return times
    
    # ========== httpx tests ==========
    async def test_httpx_default(self) -> List[float]:
        """3.1. httpx / HTTP1.1 (default)"""
        print("\n📊 3.1. httpx / HTTP1.1 (default)")
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            async with httpx.AsyncClient(http2=False) as client:
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s")
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_httpx_connection_close(self) -> List[float]:
        """3.2. httpx / HTTP1.1 + Connection: close"""
        print("\n📊 3.2. httpx / HTTP1.1 + Connection: close")
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
                print(f"   Request {i+1}: {response_time:.3f}s")
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_httpx_keep_alive_header(self) -> List[float]:
        """3.3. httpx / HTTP1.1 + Keep-Alive header"""
        print("\n📊 3.3. httpx / HTTP1.1 + Keep-Alive header")
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
                print(f"   Request {i+1}: {response_time:.3f}s")
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_httpx_session_reuse(self) -> List[float]:
        """3.4. httpx / HTTP1.1 + Client reuse"""
        print("\n📊 3.4. httpx / HTTP1.1 + Client reuse")
        times = []
        
        async with httpx.AsyncClient(http2=False) as client:
            for i in range(3):
                url = f"{self.base_url}?start={i}&end={i}"
                start = time.time()
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s")
                await asyncio.sleep(0.5)
        
        return times
    
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
        
        return results
    
    def display_results_table(self, results: Dict[str, List[float]]):
        """結果をテーブル形式で表示"""
        print("\n" + "=" * 100)
        print("📋 HTTP CONNECTION PERFORMANCE RESULTS")
        print("=" * 100)
        
        # ヘッダー
        print(f"{'Pattern':<35} {'Req1 (s)':<10} {'Req2 (s)':<10} {'Req3 (s)':<10} {'Average (s)':<12} {'Analysis'}")
        print("-" * 100)
        
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
                
                if improvement > 20:
                    analysis = "🚀 Strong improvement"
                elif improvement > 10:
                    analysis = "✅ Good improvement"
                elif improvement > 5:
                    analysis = "⚠️ Slight improvement"
                else:
                    analysis = "➖ Consistent performance"
            else:
                analysis = "📊 N/A"
            
            print(f"{description:<35} {times[0]:<10.3f} {times[1]:<10.3f} {times[2]:<10.3f} {avg:<12.3f} {analysis}")
        
        # 統計分析
        print("\n" + "=" * 100)
        print("📊 STATISTICAL ANALYSIS")
        print("=" * 100)
        
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
    tester = HTTPConnectionPerformanceTester()
    
    # 全テスト実行
    results = await tester.run_all_tests()
    
    # 結果表示
    tester.display_results_table(results)

if __name__ == "__main__":
    asyncio.run(main())

class HTTPConnectionPerformanceTester:
    def __init__(self):
        self.base_url = "https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries"
        self.warm_up_url = f"{self.base_url}?start=0&end=0"
    
    def warm_up(self):
        """DNS cache等のwarm up"""
        print("🔥 Warming up (DNS cache, SSL handshake)...")
        try:
            resp = requests.get(self.warm_up_url, timeout=10)
            print(f"   Warm up completed: {resp.status_code}")
        except Exception as e:
            print(f"   Warm up failed: {e}")
        time.sleep(1)
    
    # ========== requests tests ==========
    def test_requests_default(self) -> List[float]:
        """1.1. requests / HTTP1.1 (default)"""
        print("\n� 1.1. requests / HTTP1.1 (default)")
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i+10}&end={i+10}"
            start = time.time()
            resp = requests.get(url)
            end = time.time()
            response_time = end - start
            times.append(response_time)
            print(f"   Request {i+1}: {response_time:.3f}s")
            time.sleep(0.5)
        
        return times
    
    def test_requests_connection_close(self) -> List[float]:
        """1.2. requests / HTTP1.1 + Connection: close"""
        print("\n📊 1.2. requests / HTTP1.1 + Connection: close")
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i}&end={i}"
            start = time.time()
            resp = requests.get(url, headers={'Connection': 'close'})
            end = time.time()
            response_time = end - start
            times.append(response_time)
            print(f"   Request {i+1}: {response_time:.3f}s")
            time.sleep(0.5)
        
        return times
    
    def test_requests_keep_alive_header(self) -> List[float]:
        """1.3. requests / HTTP1.1 + Keep-Alive header"""
        print("\n� 1.3. requests / HTTP1.1 + Keep-Alive header")
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i+30}&end={i+30}"
            start = time.time()
            resp = requests.get(url, headers={'Connection': 'keep-alive'})
            end = time.time()
            response_time = end - start
            times.append(response_time)
            print(f"   Request {i+1}: {response_time:.3f}s")
            time.sleep(0.5)
        
        return times
    
    def test_requests_session(self) -> List[float]:
        """1.4. requests / HTTP1.1 + Session (connection reuse)"""
        print("\n� 1.4. requests / HTTP1.1 + Session (connection reuse)")
        times = []
        
        with requests.Session() as session:
            for i in range(3):
                url = f"{self.base_url}?start={i+40}&end={i+40}"
                start = time.time()
                resp = session.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s")
                time.sleep(0.5)
        
        return times
    
    # ========== aiohttp tests ==========
    async def test_aiohttp_default(self) -> List[float]:
        """2.1. aiohttp / HTTP1.1 (default)"""
        print("\n📊 2.1. aiohttp / HTTP1.1 (default)")
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
                    print(f"   Request {i+1}: {response_time:.3f}s")
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_aiohttp_connection_close(self) -> List[float]:
        """2.2. aiohttp / HTTP1.1 + Connection: close"""
        print("\n� 2.2. aiohttp / HTTP1.1 + Connection: close")
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i+60}&end={i+60}"
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
                    print(f"   Request {i+1}: {response_time:.3f}s")
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_aiohttp_keep_alive_header(self) -> List[float]:
        """2.3. aiohttp / HTTP1.1 + Keep-Alive header"""
        print("\n� 2.3. aiohttp / HTTP1.1 + Keep-Alive header")
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i+70}&end={i+70}"
            start = time.time()
            async with aiohttp.ClientSession(
                headers={'Connection': 'keep-alive'}
            ) as session:
                async with session.get(url) as resp:
                    await resp.text()
                    end = time.time()
                    response_time = end - start
                    times.append(response_time)
                    print(f"   Request {i+1}: {response_time:.3f}s")
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_aiohttp_session_reuse(self) -> List[float]:
        """2.4. aiohttp / HTTP1.1 + Session reuse"""
        print("\n� 2.4. aiohttp / HTTP1.1 + Session reuse")
        times = []
        
        async with aiohttp.ClientSession() as session:
            for i in range(3):
                url = f"{self.base_url}?start={i+80}&end={i+80}"
                start = time.time()
                async with session.get(url) as resp:
                    await resp.text()
                    end = time.time()
                    response_time = end - start
                    times.append(response_time)
                    print(f"   Request {i+1}: {response_time:.3f}s")
                await asyncio.sleep(0.5)
        
        return times
    
    # ========== httpx tests ==========
    async def test_httpx_default(self) -> List[float]:
        """3.1. httpx / HTTP1.1 (default)"""
        print("\n� 3.1. httpx / HTTP1.1 (default)")
        times = []
        
        for i in range(3):
            url = f"{self.base_url}?start={i+90}&end={i+90}"
            start = time.time()
            async with httpx.AsyncClient(http2=False) as client:
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s")
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_httpx_connection_close(self) -> List[float]:
        """3.2. httpx / HTTP1.1 + Connection: close"""
        print("\n📊 3.2. httpx / HTTP1.1 + Connection: close")
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
                print(f"   Request {i+1}: {response_time:.3f}s")
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_httpx_keep_alive_header(self) -> List[float]:
        """3.3. httpx / HTTP1.1 + Keep-Alive header"""
        print("\n📊 3.3. httpx / HTTP1.1 + Keep-Alive header")
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
                print(f"   Request {i+1}: {response_time:.3f}s")
            await asyncio.sleep(0.5)
        
        return times
    
    async def test_httpx_session_reuse(self) -> List[float]:
        """3.4. httpx / HTTP1.1 + Client reuse"""
        print("\n📊 3.4. httpx / HTTP1.1 + Client reuse")
        times = []
        
        async with httpx.AsyncClient(http2=False) as client:
            for i in range(3):
                url = f"{self.base_url}?start={i}&end={i}"
                start = time.time()
                resp = await client.get(url)
                end = time.time()
                response_time = end - start
                times.append(response_time)
                print(f"   Request {i+1}: {response_time:.3f}s")
                await asyncio.sleep(0.5)
        
        return times
    
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
        
        return results
    
    def display_results_table(self, results: Dict[str, List[float]]):
        """結果をテーブル形式で表示"""
        print("\n" + "=" * 100)
        print("📋 HTTP CONNECTION PERFORMANCE RESULTS")
        print("=" * 100)
        
        # ヘッダー
        print(f"{'Pattern':<35} {'Req1 (s)':<10} {'Req2 (s)':<10} {'Req3 (s)':<10} {'Average (s)':<12} {'Analysis'}")
        print("-" * 100)
        
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
                
                if improvement > 20:
                    analysis = "🚀 Strong improvement"
                elif improvement > 10:
                    analysis = "✅ Good improvement"
                elif improvement > 5:
                    analysis = "⚠️ Slight improvement"
                else:
                    analysis = "➖ Consistent performance"
            else:
                analysis = "� N/A"
            
            print(f"{description:<35} {times[0]:<10.3f} {times[1]:<10.3f} {times[2]:<10.3f} {avg:<12.3f} {analysis}")
        
        # 統計分析
        print("\n" + "=" * 100)
        print("📊 STATISTICAL ANALYSIS")
        print("=" * 100)
        
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
    tester = HTTPConnectionPerformanceTester()
    
    # 全テスト実行
    results = await tester.run_all_tests()
    
    # 結果表示
    tester.display_results_table(results)

if __name__ == "__main__":
    asyncio.run(main())
