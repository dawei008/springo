#!/usr/bin/env python3
"""
Test models with /v1/messages-auto endpoint (the one the Electron app uses)
"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:8080"

# All models from frontend selector
TEST_MODELS = [
    ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
    ("deepseek-r1", "DeepSeek R1"),
    ("minimax-m2", "MiniMax M2"),
    ("qwen3-32b", "Qwen 3 32B"),
    ("kimi-k2", "Kimi K2"),
]

def test_model_auto(model: str, description: str):
    """Test a model with /v1/messages-auto (like the Electron app)"""
    print(f"\n{'='*60}")
    print(f"Testing: {model} - {description} (AUTO)")
    print("="*60)

    # Same format as the Electron app sends
    payload = {
        "model": model,
        "max_tokens": 4096,
        "stream": True,
        "messages": [
            {"role": "user", "content": "What is 2+2? Answer briefly."}
        ]
    }

    start_time = time.time()
    full_text = ""
    has_error = False
    error_msg = ""

    try:
        response = requests.post(
            f"{BASE_URL}/v1/messages-auto",  # The auto endpoint
            json=payload,
            stream=True,
            timeout=60
        )

        if response.status_code != 200:
            print(f"  Status: FAILED - HTTP {response.status_code}")
            print(f"  Error: {response.text[:500]}")
            return False

        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data = line[6:]
                    try:
                        event = json.loads(data)
                        event_type = event.get('type')

                        if event_type == 'content_block_delta':
                            delta = event.get('delta', {})
                            text = delta.get('text', '')
                            full_text += text
                        elif event_type == 'error':
                            has_error = True
                            error_msg = str(event)
                            break
                    except json.JSONDecodeError:
                        pass

        latency = (time.time() - start_time) * 1000

        if has_error:
            print(f"  Status: FAILED - Error event")
            print(f"  Error: {error_msg[:300]}")
            return False
        elif full_text:
            print(f"  Status: SUCCESS ({latency:.0f}ms)")
            print(f"  Response: {full_text[:100]}...")
            return True
        else:
            print(f"  Status: FAILED - No content received")
            return False

    except Exception as e:
        print(f"  Status: FAILED - Exception: {e}")
        return False

def main():
    print("Messages-Auto Endpoint Test")
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
        success = test_model_auto(model, description)
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
