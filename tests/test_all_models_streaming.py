#!/usr/bin/env python3
"""
Test all models with streaming mode (like the Electron app uses)
"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:8080"

# All models from frontend selector
TEST_MODELS = [
    ("claude-opus-4-5-20251101", "Claude Opus 4.5"),
    ("claude-sonnet-4-5-20250929", "Claude Sonnet 4.5"),
    ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
    ("deepseek-r1", "DeepSeek R1"),
    ("minimax-m2", "MiniMax M2"),
    ("qwen3-32b", "Qwen 3 32B"),
    ("kimi-k2", "Kimi K2"),
]

def test_model_streaming(model: str, description: str):
    """Test a model with streaming (like the Electron app)"""
    print(f"\n{'='*60}")
    print(f"Testing: {model} - {description} (STREAMING)")
    print("="*60)

    payload = {
        "model": model,
        "max_tokens": 200,
        "stream": True,  # Enable streaming like the app
        "messages": [
            {"role": "user", "content": "What is 2+2? Answer briefly."}
        ]
    }

    start_time = time.time()
    full_text = ""

    try:
        response = requests.post(
            f"{BASE_URL}/v1/messages",
            json=payload,
            stream=True,
            timeout=60
        )

        latency = (time.time() - start_time) * 1000

        if response.status_code == 200:
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = line[6:]
                        try:
                            event = json.loads(data)
                            if event.get('type') == 'content_block_delta':
                                delta = event.get('delta', {})
                                text = delta.get('text', '')
                                full_text += text
                            elif event.get('type') == 'error':
                                print(f"  Status: FAILED - Stream error")
                                print(f"  Error: {event}")
                                return False
                        except json.JSONDecodeError:
                            pass

            if full_text:
                print(f"  Status: SUCCESS ({latency:.0f}ms)")
                print(f"  Response: {full_text[:100]}...")
                return True
            else:
                print(f"  Status: FAILED - No content received")
                return False
        else:
            print(f"  Status: FAILED - HTTP {response.status_code}")
            print(f"  Error: {response.text[:300]}")
            return False

    except Exception as e:
        print(f"  Status: FAILED - Exception: {e}")
        return False

def main():
    print("All Models Streaming Test")
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
        success = test_model_streaming(model, description)
        results.append((model, success))
        time.sleep(1)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print("="*60)
    passed = sum(1 for _, s in results if s)
    print(f"Passed: {passed}/{len(results)}")
    print()
    for model, success in results:
        status = "PASS" if success else "FAIL"
        print(f"  {model}: {status}")

if __name__ == "__main__":
    main()
