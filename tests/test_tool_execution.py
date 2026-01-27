#!/usr/bin/env python3
"""
Test tool execution with different models
"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:8080"

# Models to test tool execution
TEST_MODELS = [
    ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
    ("qwen3-32b", "Qwen 3 32B"),
]

def test_tool_execution(model: str, description: str):
    """Test tool execution with a model"""
    print(f"\n{'='*60}")
    print(f"Testing Tool Execution: {model} - {description}")
    print("="*60)

    # Request that should trigger tool use (web search or read file)
    payload = {
        "model": model,
        "max_tokens": 1000,
        "stream": True,
        "messages": [
            {"role": "user", "content": "What files are in the current directory? Use the glob tool to find *.py files."}
        ]
    }

    start_time = time.time()
    full_text = ""
    tool_calls = []
    tool_results = []

    try:
        response = requests.post(
            f"{BASE_URL}/v1/messages-auto",
            json=payload,
            stream=True,
            timeout=120
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
                            if 'text' in delta:
                                full_text += delta['text']
                        elif event_type == 'tool_execution_start':
                            tools = event.get('tools', [])
                            tool_calls.extend(tools)
                            print(f"  Tool call: {[t['name'] for t in tools]}")
                        elif event_type == 'tool_result':
                            tool_results.append(event)
                            print(f"  Tool result: {event.get('tool_name')} completed")
                        elif event_type == 'error':
                            print(f"  Error event: {event}")
                    except json.JSONDecodeError:
                        pass

        latency = (time.time() - start_time) * 1000

        if tool_calls:
            print(f"  Status: SUCCESS with TOOLS ({latency:.0f}ms)")
            print(f"  Tools used: {[t['name'] for t in tool_calls]}")
            print(f"  Response: {full_text[:200]}...")
            return True
        elif full_text:
            print(f"  Status: SUCCESS but NO TOOLS ({latency:.0f}ms)")
            print(f"  Response: {full_text[:200]}...")
            return True
        else:
            print(f"  Status: FAILED - No content or tools")
            return False

    except Exception as e:
        print(f"  Status: FAILED - Exception: {e}")
        return False

def main():
    print("Tool Execution Test")
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
        success = test_tool_execution(model, description)
        results.append((model, success))
        time.sleep(2)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print("="*60)
    for model, success in results:
        status = "PASS" if success else "FAIL"
        print(f"  {model}: {status}")

if __name__ == "__main__":
    main()
