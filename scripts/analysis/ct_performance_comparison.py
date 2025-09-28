#!/usr/bin/env python3
"""
CT API Performance Comparison Script

This script compares the performance of requests library vs aiohttp with keep-alive
for CT log API endpoints. It measures execution time and TCP handshakes for both methods.

IMPORTANT NOTE: Google CT API uses HTTP/2 protocol with ALPN negotiation.
HTTP/2 multiplexes multiple streams over a single TCP connection, which affects
traditional keep-alive behavior analysis. Each request may create new streams
rather than new TCP connections.
"""

import asyncio
import aiohttp
import requests
import time
import logging
import subprocess
import json
from typing import Dict, List, Tuple
import argparse
from tabulate import tabulate


class NetworkStats:
    """Helper class to monitor TCP connections and estimate handshakes"""
    
    @staticmethod
    def get_process_connections() -> Dict[str, int]:
        """Get current process TCP connections to ct.googleapis.com"""
        try:
            import os
            pid = os.getpid()
            
            # Use lsof to get connections for current process
            result = subprocess.run(['lsof', '-p', str(pid), '-i', 'tcp'], 
                                  capture_output=True, text=True)
            
            connections = {'ct_googleapis_connections': 0, 'total_tcp_connections': 0}
            
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'ct.googleapis.com' in line and 'ESTABLISHED' in line:
                        connections['ct_googleapis_connections'] += 1
                    elif 'tcp' in line.lower() and ('ESTABLISHED' in line or 'TIME_WAIT' in line):
                        connections['total_tcp_connections'] += 1
            
            logging.debug(f"Process connections: {connections}")
            return connections
            
        except Exception as e:
            logging.debug(f"Failed to get process connections: {e}")
            # Fallback to netstat approach
            return NetworkStats._fallback_netstat_count()
    
    @staticmethod
    def _fallback_netstat_count() -> Dict[str, int]:
        """Fallback method using netstat to count CT API connections"""
        try:
            result = subprocess.run(['netstat', '-an'], capture_output=True, text=True)
            if result.returncode != 0:
                return {'ct_googleapis_connections': 0, 'total_tcp_connections': 0}
            
            connections = {'ct_googleapis_connections': 0, 'total_tcp_connections': 0}
            
            for line in result.stdout.split('\n'):
                if 'tcp' in line.lower():
                    # Look for connections to CT API (port 443)
                    if ('ct.googleapis.com' in line or '173.194.' in line or '142.250.' in line) and 'ESTABLISHED' in line:
                        connections['ct_googleapis_connections'] += 1
                    elif 'ESTABLISHED' in line:
                        connections['total_tcp_connections'] += 1
            
            logging.debug(f"Fallback netstat connections: {connections}")
            return connections
            
        except Exception as e:
            logging.debug(f"Fallback netstat failed: {e}")
            return {'ct_googleapis_connections': 0, 'total_tcp_connections': 0}
    
    @staticmethod
    def calculate_new_connections(before: Dict[str, int], after: Dict[str, int]) -> int:
        """Estimate new connections created during the test"""
        if not before or not after:
            return 0
        
        # Use CT-specific connections if available, otherwise use total
        key = 'ct_googleapis_connections' if 'ct_googleapis_connections' in before else 'total_tcp_connections'
        
        if key in before and key in after:
            new_connections = max(0, after[key] - before[key])
            return new_connections
        
        return 0
    


class RequestsPerformanceTester:
    """Performance tester using requests library (without keep-alive)"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        # No session - each request creates new connection
        self.session = None
        
    def make_request(self, start: int, end: int, request_index: int = 0) -> Tuple[bool, float, int]:
        """Make a single request and return (success, response_time, local_port)"""
        url = f"{self.base_url}?start={start}&end={end}"
        request_start = time.time()
        
        try:
            if self.session:
                response = self.session.get(url, timeout=30, stream=True)
            else:
                response = requests.get(url, timeout=30, stream=True)
            
            request_time = time.time() - request_start
            success = response.status_code == 200
            
            # Get socket information to detect connection reuse
            local_port = 0
            try:
                if hasattr(response, 'raw') and response.raw:
                    if hasattr(response.raw, '_original_response'):
                        orig_response = response.raw._original_response
                        if hasattr(orig_response, 'fp') and orig_response.fp:
                            if hasattr(orig_response.fp, 'raw') and orig_response.fp.raw:
                                if hasattr(orig_response.fp.raw, '_sock'):
                                    sock = orig_response.fp.raw._sock
                                    if sock:
                                        local_port = sock.getsockname()[1]
                                        logging.debug(f"Requests {request_index+1} to {start}-{end} used local port: {local_port}")
                
                if local_port == 0:
                    logging.debug(f"Could not get socket info for requests {request_index+1}")
                
            except Exception as e:
                logging.debug(f"Failed to get socket info for requests {request_index+1}: {e}")
            
            # Close response to return connection to pool
            response.close()
            
            return success, request_time, local_port
            
        except Exception as e:
            request_time = time.time() - request_start
            logging.error(f"Request failed: {e}")
            return False, request_time, 0
    
    def run_test(self, num_requests: int, increment: int = 32, 
                 delay: float = 1.0) -> Dict:
        """Run performance test with requests"""
        logging.info(f"Starting requests test ({num_requests} requests)")
        
        start_time = time.time()
        results = []
        current_start = 0
        current_end = 31
        
        # Track TCP connections using socket port monitoring
        used_ports = set()
        total_new_connections = 0
        
        for i in range(num_requests):
            success, req_time, local_port = self.make_request(current_start, current_end, i)
            
            # Count new connections by tracking unique local ports
            if local_port > 0:
                if local_port not in used_ports:
                    used_ports.add(local_port)
                    total_new_connections += 1
                    logging.info(f"Request {i+1}: New TCP connection on port {local_port} (total unique: {len(used_ports)})")
                else:
                    logging.debug(f"Request {i+1}: Reused connection on port {local_port}")
            
            results.append({
                'index': i + 1,
                'start': current_start,
                'end': current_end,
                'success': success,
                'response_time': req_time,
                'local_port': local_port
            })
            
            current_start += increment
            current_end += increment
            
            # Sleep between requests
            if delay > 0 and i < num_requests - 1:
                time.sleep(delay)
        
        total_time = time.time() - start_time
        
        # Use actual connection count from port tracking
        tcp_handshakes = total_new_connections
        
        logging.info(f"Requests used {tcp_handshakes} TCP handshakes (port monitoring detected: {total_new_connections}, ports: {sorted(used_ports)})")
        
        # Calculate statistics
        successful_requests = sum(1 for r in results if r['success'])
        avg_response_time = sum(r['response_time'] for r in results) / len(results)
        
        return {
            'method': 'requests',
            'total_time': total_time,
            'successful_requests': successful_requests,
            'failed_requests': num_requests - successful_requests,
            'avg_response_time': avg_response_time,
            'tcp_handshakes': tcp_handshakes,
            'results': results
        }
    
    def close(self):
        """Close the session if it exists"""
        if self.session:
            self.session.close()


class ConnectionPoolDetector:
    """Detects new TCP connections by monitoring aiohttp connection pool"""
    
    def __init__(self):
        self.connection_history = []
        self.request_count = 0
    
    def get_pool_connection_ids(self, connector) -> Dict[str, List[int]]:
        """Get current connection IDs from the connection pool"""
        pool_state = {}
        for key, conns in connector._conns.items():
            key_str = str(key)
            pool_state[key_str] = [id(conn) for conn in conns]
        return pool_state
    
    def detect_new_connections(self, pre_pool_ids: Dict[str, List[int]], 
                              post_pool_ids: Dict[str, List[int]]) -> int:
        """Count new connections by comparing connection IDs"""
        new_connection_count = 0
        
        for key_str in post_pool_ids:
            pre_ids = set(pre_pool_ids.get(key_str, []))
            post_ids = set(post_pool_ids[key_str])
            
            # Count new connection IDs
            new_ids = post_ids - pre_ids
            if new_ids:
                new_connection_count += len(new_ids)
                logging.debug(f"🔄 NEW CONNECTION detected for {key_str}: {len(new_ids)} connections")
        
        return new_connection_count

class AiohttpPerformanceTester:
    """Performance tester using aiohttp with keep-alive"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.connection_detector = ConnectionPoolDetector()
        
    async def make_request(self, session: aiohttp.ClientSession, 
                          start: int, end: int, request_index: int = 0) -> Tuple[bool, float, int, Dict[str, List[int]]]:
        """Make a single async request and return (success, response_time, local_port, post_connection_ids)"""
        url = f"{self.base_url}?start={start}&end={end}"
        request_start = time.time()
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                await response.text()  # Read response body
                request_time = time.time() - request_start
                success = response.status == 200
                
                # Get socket information to detect connection reuse
                local_port = 0
                try:
                    conn = response.connection
                    if conn and hasattr(conn, 'transport') and conn.transport:
                        sock = conn.transport.get_extra_info("socket")
                        if sock:
                            local_port = sock.getsockname()[1]
                            logging.debug(f"Request {request_index+1} to {start}-{end} used local port: {local_port}")
                        else:
                            logging.debug(f"Socket not available from transport for request {request_index+1}")
                    else:
                        logging.debug(f"Connection or transport not available for request {request_index+1}")
                except Exception as e:
                    logging.debug(f"Failed to get socket info for request {request_index+1}: {e}")
                
                # Get connection pool state inside the session context
                post_connection_ids = {}
                try:
                    session_connector = session.connector
                    for key, conns in session_connector._conns.items():
                        key_str = str(key)
                        post_connection_ids[key_str] = [id(conn) for conn in conns]
                    logging.debug(f"Request {request_index+1} post-connection pool state: {post_connection_ids}")
                except Exception as e:
                    logging.debug(f"Failed to get post-connection pool state for request {request_index+1}: {e}")
                
                return success, request_time, local_port, post_connection_ids
                
        except Exception as e:
            request_time = time.time() - request_start
            logging.error(f"Async request {request_index+1} failed: {e}")
            return False, request_time, 0, {}
    
    async def run_test(self, num_requests: int, increment: int = 32, 
                      delay: float = 1.0) -> Dict:
        """Run performance test with aiohttp"""
        logging.info(f"Starting aiohttp test ({num_requests} requests)")
        
        start_time = time.time()
        results = []
        current_start = 0
        current_end = 31
        
        # Create connector with keep-alive settings
        connector = aiohttp.TCPConnector(
            limit=10,  # Max number of connections
            limit_per_host=5,  # Max connections per host
            keepalive_timeout=30,  # Keep-alive timeout
            enable_cleanup_closed=True
        )
        
        # Track TCP connections using connection pool monitoring
        total_new_connections = 0
        
        async with aiohttp.ClientSession(connector=connector) as session:
            # Get initial connection pool state from session's connector
            session_connector = session.connector
            pre_pool_ids = self.connection_detector.get_pool_connection_ids(session_connector)
            logging.debug(f"Initial pool state: {pre_pool_ids}")
            
            for i in range(num_requests):
                # Monitor connection pool before request
                pre_request_pool_ids = self.connection_detector.get_pool_connection_ids(session_connector)
                logging.debug(f"🔴Pre-request pool state for request {i+1}: {pre_request_pool_ids}")
                
                success, req_time, local_port, post_connection_ids = await self.make_request(session, current_start, current_end, i)
                
                # Use connection pool state from inside the session context
                logging.debug(f"🟢Post-request pool state from session context for request {i+1}: {post_connection_ids}, local_port: {local_port}")
                
                # Detect new connections for this request using data from session context
                new_connections = self.connection_detector.detect_new_connections(
                    pre_request_pool_ids, post_connection_ids
                )
                total_new_connections += new_connections
                
                results.append({
                    'index': i + 1,
                    'start': current_start,
                    'end': current_end,
                    'success': success,
                    'response_time': req_time,
                    'local_port': local_port,
                    'new_connections': new_connections
                })
                
                if new_connections > 0:
                    logging.info(f"Request {i+1}: {new_connections} new TCP connection(s) established")
                
                current_start += increment
                current_end += increment
                
                # Sleep between requests
                if delay > 0 and i < num_requests - 1:
                    await asyncio.sleep(delay)
            
            # Final pool state
            final_pool_ids = self.connection_detector.get_pool_connection_ids(session_connector)
            logging.debug(f"Final pool state: {final_pool_ids}")
        
        # Use actual connection count from pool monitoring
        tcp_handshakes = total_new_connections
        
        logging.info(f"Aiohttp used {tcp_handshakes} TCP handshakes (pool monitoring detected: {total_new_connections})")
        
        total_time = time.time() - start_time
        
        # Calculate statistics
        successful_requests = sum(1 for r in results if r['success'])
        avg_response_time = sum(r['response_time'] for r in results) / len(results)
        
        return {
            'method': 'aiohttp',
            'total_time': total_time,
            'successful_requests': successful_requests,
            'failed_requests': num_requests - successful_requests,
            'avg_response_time': avg_response_time,
            'tcp_handshakes': tcp_handshakes,
            'results': results
        }


def format_results_table(requests_result: Dict, aiohttp_result: Dict) -> str:
    """Format comparison results as a table"""
    
    # Calculate differences
    time_diff = aiohttp_result['total_time'] - requests_result['total_time']
    handshake_diff = aiohttp_result['tcp_handshakes'] - requests_result['tcp_handshakes']
    
    # Prepare table data
    headers = ['Metric', 'Requests', 'Aiohttp (Keep-Alive)', 'Difference']
    
    table_data = [
        ['Total Time (s)', 
         f"{requests_result['total_time']:.2f}", 
         f"{aiohttp_result['total_time']:.2f}", 
         f"{time_diff:+.2f}"],
        
        ['Successful Requests', 
         requests_result['successful_requests'], 
         aiohttp_result['successful_requests'], 
         aiohttp_result['successful_requests'] - requests_result['successful_requests']],
        
        ['Failed Requests', 
         requests_result['failed_requests'], 
         aiohttp_result['failed_requests'], 
         aiohttp_result['failed_requests'] - requests_result['failed_requests']],
        
        ['Avg Response Time (s)', 
         f"{requests_result['avg_response_time']:.3f}", 
         f"{aiohttp_result['avg_response_time']:.3f}", 
         f"{aiohttp_result['avg_response_time'] - requests_result['avg_response_time']:+.3f}"],
        
        ['TCP Handshakes', 
         requests_result['tcp_handshakes'], 
         aiohttp_result['tcp_handshakes'], 
         f"{handshake_diff:+d}"],
        
        ['Requests/Second', 
         f"{requests_result['successful_requests'] / requests_result['total_time']:.2f}", 
         f"{aiohttp_result['successful_requests'] / aiohttp_result['total_time']:.2f}", 
         f"{(aiohttp_result['successful_requests'] / aiohttp_result['total_time']) - (requests_result['successful_requests'] / requests_result['total_time']):+.2f}"]
    ]
    
    return tabulate(table_data, headers=headers, tablefmt='grid')


async def main():
    parser = argparse.ArgumentParser(description="Compare requests vs aiohttp performance for CT API")
    parser.add_argument("--base_url", type=str, 
                       default="https://ct.googleapis.com/logs/us1/argon2026h1/ct/v1/get-entries",
                       help="Base URL for CT log API")
    parser.add_argument("--num_requests", type=int, default=500,
                       help="Number of requests to send (default: 500)")
    parser.add_argument("--increment", type=int, default=32,
                       help="Increment for start/end parameters (default: 32)")
    parser.add_argument("--delay", type=float, default=1.0,
                       help="Delay between requests in seconds (default: 1.0)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Starting CT API Performance Comparison")
    logger.info(f"Base URL: {args.base_url}")
    logger.info(f"Number of requests: {args.num_requests}")
    logger.info(f"Increment: {args.increment}")
    logger.info(f"Delay between requests: {args.delay}s")
    
    print("\n" + "="*80)
    print("CT API PERFORMANCE COMPARISON")
    print("="*80)
    
    # Test 1: requests library (without keep-alive)
    print("\n🔄 Running requests library test...")
    requests_tester = RequestsPerformanceTester(args.base_url)
    requests_result = requests_tester.run_test(args.num_requests, args.increment, args.delay)
    requests_tester.close()
    
    print(f"✅ Requests test completed in {requests_result['total_time']:.2f}s")
    
    # Small delay between tests
    print("\n⏳ Waiting 5 seconds before next test...")
    await asyncio.sleep(5)
    
    # Test 2: aiohttp with keep-alive
    print("\n🔄 Running aiohttp with keep-alive test...")
    aiohttp_tester = AiohttpPerformanceTester(args.base_url)
    aiohttp_result = await aiohttp_tester.run_test(args.num_requests, args.increment, args.delay)
    
    print(f"✅ Aiohttp test completed in {aiohttp_result['total_time']:.2f}s")
    
    # Display results
    print("\n" + "="*80)
    print("PERFORMANCE COMPARISON RESULTS")
    print("="*80)
    
    results_table = format_results_table(requests_result, aiohttp_result)
    print("\n" + results_table)
    
    # Performance analysis
    print("\n" + "="*80)
    print("ANALYSIS")
    print("="*80)
    
    time_improvement = ((requests_result['total_time'] - aiohttp_result['total_time']) / requests_result['total_time']) * 100
    handshake_reduction = requests_result['tcp_handshakes'] - aiohttp_result['tcp_handshakes']
    
    if time_improvement > 0:
        print(f"🚀 Aiohttp with keep-alive was {time_improvement:.1f}% faster")
    else:
        print(f"🐌 Aiohttp with keep-alive was {abs(time_improvement):.1f}% slower")
    
    if handshake_reduction > 0:
        print(f"🔗 Keep-alive reduced TCP handshakes by {handshake_reduction} ({(handshake_reduction/requests_result['tcp_handshakes']*100):.1f}%)")
    elif handshake_reduction < 0:
        print(f"🔗 Aiohttp used {abs(handshake_reduction)} more TCP handshakes")
    else:
        print("🔗 Both methods used the same number of TCP handshakes")
    
    print(f"\n📊 Final Statistics:")
    print(f"   - Total requests sent: {args.num_requests}")
    print(f"   - Requests successful rate: {requests_result['successful_requests']}/{args.num_requests} ({requests_result['successful_requests']/args.num_requests*100:.1f}%)")
    print(f"   - Aiohttp successful rate: {aiohttp_result['successful_requests']}/{args.num_requests} ({aiohttp_result['successful_requests']/args.num_requests*100:.1f}%)")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
    except Exception as e:
        logging.error(f"Test failed with error: {e}")
        raise
