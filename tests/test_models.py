#!/usr/bin/env python3
"""
Test different models on Bedrock through Springo API
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://127.0.0.1:8080"

# Models to test
MODELS = [
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "deepseek-r1",
    "minimax-01",
    "qwen2.5-72b-instruct",
    "qwen2.5-32b-instruct",
    "kimi-k2",
]

# Test scenarios
SCENARIOS = [
    {
        "name": "Simple Q&A",
        "prompt": "What is the capital of France? Answer in one sentence.",
        "max_tokens": 100,
    },
    {
        "name": "Code Generation",
        "prompt": "Write a Python function to calculate fibonacci numbers. Keep it simple, under 10 lines.",
        "max_tokens": 300,
    },
    {
        "name": "Chinese Response",
        "prompt": "用中文简单介绍一下人工智能的发展历史，100字以内。",
        "max_tokens": 300,
    },
]

def test_model(model: str, scenario: dict) -> dict:
    """Test a single model with a scenario"""
    result = {
        "model": model,
        "scenario": scenario["name"],
        "success": False,
        "response": None,
        "error": None,
        "latency_ms": None,
    }

    payload = {
        "model": model,
        "max_tokens": scenario["max_tokens"],
        "messages": [
            {"role": "user", "content": scenario["prompt"]}
        ]
    }

    start_time = time.time()

    try:
        response = requests.post(
            f"{BASE_URL}/v1/messages",
            json=payload,
            timeout=60
        )

        latency = (time.time() - start_time) * 1000
        result["latency_ms"] = round(latency)

        if response.status_code == 200:
            data = response.json()
            if "content" in data and len(data["content"]) > 0:
                result["success"] = True
                result["response"] = data["content"][0].get("text", "")[:200]  # Truncate
            else:
                result["error"] = "No content in response"
        else:
            result["error"] = f"HTTP {response.status_code}: {response.text[:200]}"

    except requests.exceptions.Timeout:
        result["error"] = "Timeout (60s)"
    except Exception as e:
        result["error"] = str(e)[:200]

    return result

def main():
    print("=" * 70)
    print(f"Model Testing - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Check server health
    try:
        health = requests.get(f"{BASE_URL}/health", timeout=5)
        if health.status_code != 200:
            print("ERROR: Server not healthy")
            return
    except:
        print("ERROR: Cannot connect to server at", BASE_URL)
        return

    results = []

    for model in MODELS:
        print(f"\n{'='*70}")
        print(f"Testing: {model}")
        print("=" * 70)

        for scenario in SCENARIOS:
            print(f"\n  Scenario: {scenario['name']}")
            print(f"  Prompt: {scenario['prompt'][:50]}...")

            result = test_model(model, scenario)
            results.append(result)

            if result["success"]:
                print(f"  Status: SUCCESS ({result['latency_ms']}ms)")
                print(f"  Response: {result['response'][:100]}...")
            else:
                print(f"  Status: FAILED")
                print(f"  Error: {result['error']}")

            time.sleep(1)  # Rate limiting

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    summary = {}
    for r in results:
        model = r["model"]
        if model not in summary:
            summary[model] = {"success": 0, "failed": 0, "avg_latency": []}

        if r["success"]:
            summary[model]["success"] += 1
            summary[model]["avg_latency"].append(r["latency_ms"])
        else:
            summary[model]["failed"] += 1

    print(f"\n{'Model':<35} {'Success':<10} {'Failed':<10} {'Avg Latency':<15}")
    print("-" * 70)

    for model, stats in summary.items():
        avg_lat = round(sum(stats["avg_latency"]) / len(stats["avg_latency"])) if stats["avg_latency"] else "N/A"
        lat_str = f"{avg_lat}ms" if isinstance(avg_lat, int) else avg_lat
        print(f"{model:<35} {stats['success']:<10} {stats['failed']:<10} {lat_str:<15}")

    # Save results
    with open("/Users/awsdawei/claude/springo/tests/model_test_results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nDetailed results saved to: tests/model_test_results.json")

if __name__ == "__main__":
    main()
