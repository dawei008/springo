#!/usr/bin/env python3
"""
Quick test for Converse API routing for non-Claude models
"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:8080"

# Test models (all from frontend selector)
TEST_MODELS = [
    # Claude models (Anthropic API)
    ("claude-opus-4-5-20251101", "Claude Opus 4.5 (Anthropic API)"),
    ("claude-sonnet-4-5-20250929", "Claude Sonnet 4.5 (Anthropic API)"),
    ("claude-haiku-4-5-20251001", "Claude Haiku 4.5 (Anthropic API)"),
    # Non-Claude models (Converse API)
    ("deepseek-r1", "DeepSeek R1 (Converse API)"),
    ("minimax-m2", "MiniMax M2 (Converse API)"),
    ("qwen3-32b", "Qwen 3 32B (Converse API)"),
    ("kimi-k2", "Kimi K2 (Converse API)"),
]

def test_model(model: str, description: str):
    """Test a single model"""
    print(f"\n{'='*60}")
    print(f"Testing: {model} - {description}")
    print("="*60)

    payload = {
        "model": model,
        "max_tokens": 100,
        "messages": [
            {"role": "user", "content": "What is 2+2? Answer with just the number."}
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

        if response.status_code == 200:
            data = response.json()
            if "content" in data and len(data["content"]) > 0:
                text = data["content"][0].get("text", "")
                print(f"  Status: SUCCESS ({latency:.0f}ms)")
                print(f"  Response: {text[:100]}")
                return True
            else:
                print(f"  Status: FAILED - No content in response")
                print(f"  Response: {json.dumps(data, indent=2)[:500]}")
        else:
            print(f"  Status: FAILED - HTTP {response.status_code}")
            print(f"  Error: {response.text[:500]}")

    except Exception as e:
        print(f"  Status: FAILED - Exception: {e}")

    return False

def main():
    print("Converse API Routing Test")
    print("="*60)

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
    for model, description in TEST_MODELS:
        success = test_model(model, description)
        results.append((model, success))
        time.sleep(1)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print("="*60)
    for model, success in results:
        status = "PASS" if success else "FAIL"
        print(f"  {model}: {status}")

if __name__ == "__main__":
    main()
