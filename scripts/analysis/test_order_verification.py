"""
テスト実行順序を変更して、1.1 requests (no keep-alive) が本当に遅いのかを検証
kernelレベルやOSレベルの接続キャッシュの影響を調査
"""
import requests
import aiohttp
import httpx
import asyncio
import time
import random

class OrderVerificationTester:
    def __init__(self):
        self.base_url = "https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries"
    
    def test_requests_no_keepalive_single(self, iteration, url_param):
        """単体でrequests no keep-aliveをテスト"""
        url = f"{self.base_url}?start={url_param}&end={url_param}"
        start = time.time()
        # 明示的にConnection: closeを設定
        resp = requests.get(url, headers={'Connection': 'close'})
        end = time.time()
        response_time = end - start
        print(f"  Iteration {iteration}: {response_time:.3f}s (Status: {resp.status_code})")
        return response_time
    
    def test_requests_keepalive_single(self, session, iteration, url_param):
        """単体でrequests keep-aliveをテスト"""
        url = f"{self.base_url}?start={url_param}&end={url_param}"
        start = time.time()
        resp = session.get(url)
        end = time.time()
        response_time = end - start
        print(f"  Iteration {iteration}: {response_time:.3f}s (Status: {resp.status_code})")
        return response_time
    
    async def test_httpx_http2_single(self, client, iteration, url_param):
        """単体でhttpx HTTP/2をテスト"""
        url = f"{self.base_url}?start={url_param}&end={url_param}"
        start = time.time()
        resp = await client.get(url)
        end = time.time()
        response_time = end - start
        print(f"  Iteration {iteration}: {response_time:.3f}s (Status: {resp.status_code}, Version: {resp.http_version})")
        return response_time

    def test_pattern_1_first(self):
        """パターン1: requests no keep-aliveを最初に実行"""
        print("\n" + "="*70)
        print("【パターン1: requests no keep-alive → 他のテスト】")
        print("="*70)
        
        # 1. requests no keep-alive (最初)
        print("\n🔴 1. requests no keep-alive (最初に実行)")
        times_no_keepalive = []
        for i in range(3):
            time_taken = self.test_requests_no_keepalive_single(i+1, i)
            times_no_keepalive.append(time_taken)
            time.sleep(0.5)
        
        # 2. requests keep-alive
        print("\n🟢 2. requests keep-alive")
        times_keepalive = []
        session = requests.Session()
        for i in range(3):
            time_taken = self.test_requests_keepalive_single(session, i+1, i+10)
            times_keepalive.append(time_taken)
            time.sleep(0.1)
        session.close()
        
        return {
            'no_keepalive': times_no_keepalive,
            'keepalive': times_keepalive
        }
    
    def test_pattern_2_last(self):
        """パターン2: 他のテスト → requests no keep-aliveを最後に実行"""
        print("\n" + "="*70)
        print("【パターン2: 他のテスト → requests no keep-alive】")
        print("="*70)
        
        # 1. requests keep-alive (最初)
        print("\n🟢 1. requests keep-alive (最初に実行)")
        times_keepalive = []
        session = requests.Session()
        for i in range(3):
            time_taken = self.test_requests_keepalive_single(session, i+1, i+20)
            times_keepalive.append(time_taken)
            time.sleep(0.1)
        session.close()
        
        # 2. requests no keep-alive (最後)
        print("\n🔴 2. requests no keep-alive (最後に実行)")
        times_no_keepalive = []
        for i in range(3):
            time_taken = self.test_requests_no_keepalive_single(i+1, i+30)
            times_no_keepalive.append(time_taken)
            time.sleep(0.5)
        
        return {
            'keepalive': times_keepalive,
            'no_keepalive': times_no_keepalive
        }
    
    async def test_pattern_3_mixed(self):
        """パターン3: ランダムな順序でmix"""
        print("\n" + "="*70)
        print("【パターン3: ランダム順序でのmixテスト】")
        print("="*70)
        
        # httpx HTTP/2を先に実行
        print("\n🟦 1. httpx HTTP/2 (最初に実行)")
        times_httpx = []
        async with httpx.AsyncClient(http2=True) as client:
            for i in range(3):
                time_taken = await self.test_httpx_http2_single(client, i+1, i+40)
                times_httpx.append(time_taken)
                await asyncio.sleep(0.1)
        
        # requests no keep-aliveを実行
        print("\n🔴 2. requests no keep-alive (httpx後)")
        times_no_keepalive = []
        for i in range(3):
            time_taken = self.test_requests_no_keepalive_single(i+1, i+50)
            times_no_keepalive.append(time_taken)
            time.sleep(0.5)
        
        return {
            'httpx': times_httpx,
            'no_keepalive': times_no_keepalive
        }
    
    def test_kernel_level_investigation(self):
        """kernel/OSレベルの調査"""
        print("\n" + "="*70)
        print("【Kernel/OSレベルの接続キャッシュ調査】")
        print("="*70)
        
        print("\n🔍 1. 大きな時間間隔での no keep-aliveテスト")
        times_long_interval = []
        for i in range(3):
            print(f"\n待機中... {i+1}/3")
            if i > 0:
                time.sleep(10)  # 10秒待機
            time_taken = self.test_requests_no_keepalive_single(i+1, i+60)
            times_long_interval.append(time_taken)
        
        print("\n🔍 2. 異なるドメインでのテスト（比較用）")
        test_url = "https://httpbin.org/get"
        times_different_domain = []
        for i in range(3):
            start = time.time()
            try:
                resp = requests.get(f"{test_url}?param={i}", headers={'Connection': 'close'}, timeout=10)
                end = time.time()
                response_time = end - start
                print(f"  Different domain {i+1}: {response_time:.3f}s (Status: {resp.status_code})")
                times_different_domain.append(response_time)
            except Exception as e:
                print(f"  Different domain {i+1}: Failed ({e})")
                times_different_domain.append(0)
            time.sleep(0.5)
        
        return {
            'long_interval': times_long_interval,
            'different_domain': times_different_domain
        }

    async def run_all_patterns(self):
        """全パターンの実行"""
        print("Kernel/OS Level Connection Cache Investigation")
        print("="*70)
        print("Testing if OS-level connection caching affects results")
        
        # パターン1: requests no keep-aliveを最初
        result1 = self.test_pattern_1_first()
        
        # 間隔を空ける
        print("\n⏳ 5秒待機...")
        time.sleep(5)
        
        # パターン2: requests no keep-aliveを最後
        result2 = self.test_pattern_2_last()
        
        # 間隔を空ける
        print("\n⏳ 5秒待機...")
        time.sleep(5)
        
        # パターン3: ランダム順序
        result3 = await self.test_pattern_3_mixed()
        
        # 間隔を空ける
        print("\n⏳ 5秒待機...")
        time.sleep(5)
        
        # Kernelレベル調査
        result4 = self.test_kernel_level_investigation()
        
        # 結果分析
        self.analyze_results(result1, result2, result3, result4)
    
    def analyze_results(self, result1, result2, result3, result4):
        """結果の分析"""
        print("\n" + "="*80)
        print("【順序依存性分析結果】")
        print("="*80)
        
        # 各パターンでのno keep-aliveの平均時間
        avg1 = sum(result1['no_keepalive']) / len(result1['no_keepalive'])
        avg2 = sum(result2['no_keepalive']) / len(result2['no_keepalive'])
        avg3 = sum(result3['no_keepalive']) / len(result3['no_keepalive'])
        avg4 = sum(result4['long_interval']) / len(result4['long_interval'])
        
        print(f"\nrequests no keep-alive 平均時間:")
        print(f"  パターン1 (最初に実行): {avg1:.3f}s")
        print(f"  パターン2 (最後に実行): {avg2:.3f}s")
        print(f"  パターン3 (httpx後): {avg3:.3f}s")
        print(f"  長時間間隔テスト: {avg4:.3f}s")
        
        # 順序依存性の判定
        max_time = max(avg1, avg2, avg3, avg4)
        min_time = min(avg1, avg2, avg3, avg4)
        difference = max_time - min_time
        relative_diff = (difference / max_time) * 100
        
        print(f"\n分析:")
        print(f"  最大差: {difference:.3f}s ({relative_diff:.1f}%)")
        
        if relative_diff > 20:
            print("  🚨 大きな順序依存性を検出！")
            print("     kernel/OSレベルの接続キャッシュの影響が疑われます")
        elif relative_diff > 10:
            print("  ⚠️ 中程度の順序依存性を検出")
            print("     何らかのキャッシュ効果が働いている可能性があります")
        else:
            print("  ✅ 順序依存性は軽微")
            print("     requests no keep-aliveは一貫して同じ性能特性を示しています")
        
        # 異なるドメインとの比較
        if result4['different_domain']:
            avg_different = sum([t for t in result4['different_domain'] if t > 0]) / len([t for t in result4['different_domain'] if t > 0])
            print(f"\n  異なるドメイン平均: {avg_different:.3f}s")
            if abs(avg_different - avg1) < 0.02:
                print("     類似の性能 → kernel level cacheの影響は少ない")
            else:
                print("     性能差あり → domain specific cacheまたはDNS cache効果")

async def main():
    """メイン関数"""
    tester = OrderVerificationTester()
    await tester.run_all_patterns()

if __name__ == "__main__":
    asyncio.run(main())
