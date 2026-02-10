"""
Springo E2E Tests - Performance Benchmarks
性能基准测试
"""
import pytest
import httpx
import asyncio
import time
from typing import List, Tuple

from .conftest import DEFAULT_TEST_MODEL


# ============ Benchmark Utilities ============

async def make_concurrent_requests(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    n: int,
    json_data: dict = None
) -> Tuple[float, List[int], int]:
    """
    Make concurrent requests and return timing info.
    
    Returns:
        (total_time, status_codes, success_count)
    """
    start = time.time()
    
    async def single_request():
        try:
            if method == "GET":
                resp = await client.get(url)
            else:
                resp = await client.post(url, json=json_data)
            return resp.status_code
        except Exception as e:
            return 500
    
    tasks = [single_request() for _ in range(n)]
    status_codes = await asyncio.gather(*tasks)
    
    total_time = time.time() - start
    success_count = sum(1 for s in status_codes if s == 200)
    
    return total_time, list(status_codes), success_count


# ============ Benchmark Tests ============

@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.slow
async def test_benchmark_health_endpoint(fastapi_client: httpx.AsyncClient):
    """
    Benchmark: Health endpoint under load.
    测试健康检查端点的并发性能。
    """
    n = 100  # Number of concurrent requests
    
    total_time, status_codes, success_count = await make_concurrent_requests(
        fastapi_client, "GET", "/health", n
    )
    
    # Calculate metrics
    requests_per_second = n / total_time
    success_rate = success_count / n * 100
    
    print(f"\n{'='*50}")
    print(f"Health Endpoint Benchmark Results:")
    print(f"  Concurrent requests: {n}")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Requests/second: {requests_per_second:.2f}")
    print(f"  Success rate: {success_rate:.1f}%")
    print(f"{'='*50}")
    
    # Assertions
    assert success_rate >= 99, f"Success rate too low: {success_rate}%"
    assert requests_per_second >= 50, f"Too slow: {requests_per_second} req/s"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.slow
async def test_benchmark_tools_list_endpoint(fastapi_client: httpx.AsyncClient):
    """
    Benchmark: Tools list endpoint under load.
    测试工具列表端点的并发性能。
    """
    n = 50
    
    total_time, status_codes, success_count = await make_concurrent_requests(
        fastapi_client, "GET", "/v1/tools/list", n
    )
    
    requests_per_second = n / total_time
    success_rate = success_count / n * 100
    
    print(f"\n{'='*50}")
    print(f"Tools List Benchmark Results:")
    print(f"  Concurrent requests: {n}")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Requests/second: {requests_per_second:.2f}")
    print(f"  Success rate: {success_rate:.1f}%")
    print(f"{'='*50}")
    
    assert success_rate >= 95, f"Success rate too low: {success_rate}%"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.slow
async def test_benchmark_tool_execution(fastapi_client: httpx.AsyncClient):
    """
    Benchmark: Tool execution endpoint under load.
    测试工具执行端点的并发性能。
    """
    n = 20
    
    total_time, status_codes, success_count = await make_concurrent_requests(
        fastapi_client, "POST", "/v1/tools/execute", n,
        json_data={"name": "execute_command", "input": {"command": "echo 'test'"}}
    )
    
    requests_per_second = n / total_time
    success_rate = success_count / n * 100
    
    print(f"\n{'='*50}")
    print(f"Tool Execution Benchmark Results:")
    print(f"  Concurrent requests: {n}")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Requests/second: {requests_per_second:.2f}")
    print(f"  Success rate: {success_rate:.1f}%")
    print(f"{'='*50}")
    
    assert success_rate >= 90, f"Success rate too low: {success_rate}%"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.slow
async def test_benchmark_sessions_list(fastapi_client: httpx.AsyncClient):
    """
    Benchmark: Sessions list endpoint under load.
    测试会话列表端点的并发性能。
    """
    n = 50
    
    total_time, status_codes, success_count = await make_concurrent_requests(
        fastapi_client, "GET", "/v1/sessions", n
    )
    
    requests_per_second = n / total_time
    success_rate = success_count / n * 100
    
    print(f"\n{'='*50}")
    print(f"Sessions List Benchmark Results:")
    print(f"  Concurrent requests: {n}")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Requests/second: {requests_per_second:.2f}")
    print(f"  Success rate: {success_rate:.1f}%")
    print(f"{'='*50}")
    
    assert success_rate >= 95, f"Success rate too low: {success_rate}%"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.slow
async def test_benchmark_messages_endpoint(fastapi_client: httpx.AsyncClient):
    """
    Benchmark: Messages endpoint (non-streaming).
    测试消息端点的响应时间。
    """
    n = 10  # Fewer requests since this hits Bedrock
    
    total_time, status_codes, success_count = await make_concurrent_requests(
        fastapi_client, "POST", "/v1/messages", n,
        json_data={
            "model": DEFAULT_TEST_MODEL,
            "max_tokens": 50,
            "messages": [{"role": "user", "content": "Say hello in one word"}],
            "stream": False
        }
    )
    
    avg_time = total_time / n
    success_rate = success_count / n * 100
    
    print(f"\n{'='*50}")
    print(f"Messages Endpoint Benchmark Results:")
    print(f"  Concurrent requests: {n}")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Average per request: {avg_time:.2f}s")
    print(f"  Success rate: {success_rate:.1f}%")
    print(f"{'='*50}")
    
    # This endpoint calls Bedrock, so we expect higher latency
    assert success_rate >= 80, f"Success rate too low: {success_rate}%"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.slow
async def test_benchmark_compare_flask_fastapi(
    flask_client: httpx.AsyncClient,
    fastapi_client: httpx.AsyncClient
):
    """
    Benchmark: Compare Flask vs FastAPI performance.
    对比 Flask 和 FastAPI 的性能。
    """
    n = 50
    
    # Test FastAPI
    fastapi_time, _, fastapi_success = await make_concurrent_requests(
        fastapi_client, "GET", "/health", n
    )
    
    # Test Flask
    try:
        flask_time, _, flask_success = await make_concurrent_requests(
            flask_client, "GET", "/health", n
        )
    except Exception:
        pytest.skip("Flask server not running")
        return
    
    fastapi_rps = n / fastapi_time
    flask_rps = n / flask_time
    improvement = ((fastapi_rps - flask_rps) / flask_rps) * 100
    
    print(f"\n{'='*50}")
    print(f"Flask vs FastAPI Comparison:")
    print(f"  Requests: {n}")
    print(f"  Flask: {flask_rps:.2f} req/s ({flask_success}/{n} success)")
    print(f"  FastAPI: {fastapi_rps:.2f} req/s ({fastapi_success}/{n} success)")
    print(f"  Improvement: {improvement:+.1f}%")
    print(f"{'='*50}")
    
    # FastAPI should be reasonably close to Flask performance
    # Note: When both servers run simultaneously, there's resource contention
    # We only check that FastAPI isn't dramatically slower (50% threshold)
    assert fastapi_rps >= flask_rps * 0.5, "FastAPI significantly slower than Flask"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_latency_health_endpoint(fastapi_client: httpx.AsyncClient):
    """
    Test: Health endpoint latency.
    测试健康检查端点的延迟。
    """
    latencies = []
    
    for _ in range(10):
        start = time.time()
        resp = await fastapi_client.get("/health")
        latency = (time.time() - start) * 1000  # ms
        latencies.append(latency)
        assert resp.status_code == 200
    
    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)
    min_latency = min(latencies)
    
    print(f"\n{'='*50}")
    print(f"Health Endpoint Latency:")
    print(f"  Average: {avg_latency:.2f}ms")
    print(f"  Min: {min_latency:.2f}ms")
    print(f"  Max: {max_latency:.2f}ms")
    print(f"{'='*50}")
    
    # Health endpoint should respond within 100ms
    assert avg_latency < 100, f"Average latency too high: {avg_latency}ms"
