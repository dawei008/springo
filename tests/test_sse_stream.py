"""
Test SSE stream to check tool_execution_start event content
"""
import requests
import json


def test_sse_stream():
    """Send a request and check SSE events"""

    # First check what tools are available
    tools_response = requests.get("http://localhost:8080/v1/tools")
    tools_data = tools_response.json()
    tools = tools_data.get('tools', [])
    print(f"Available tools: {len(tools)} tools")

    # Find execute_command tool
    exec_tool = [t for t in tools if t['name'] == 'execute_command']

    url = "http://localhost:8080/v1/messages-auto"

    payload = {
        "model": "claude-sonnet-4-5-20250929",
        "max_tokens": 4096,
        "stream": True,
        "system": "You are a helpful assistant. When asked about time, use the execute_command tool with 'date' command.",
        "messages": [
            {"role": "user", "content": "请执行date命令查看现在的时间"}
        ],
        "tools": exec_tool
    }

    print(f"\nSending request...")

    with requests.post(url, json=payload, stream=True, timeout=60) as response:
        current_event = None
        for line in response.iter_lines():
            if not line:
                continue
            line = line.decode('utf-8')

            if line.startswith('event:'):
                current_event = line[7:].strip()
            elif line.startswith('data:') and current_event == 'tool_execution_start':
                # Print raw data for tool_execution_start
                print(f"\n=== RAW tool_execution_start data ===")
                print(f"Raw line: {line}")
                data_str = line[5:].strip()
                print(f"Data string: {data_str}")
                try:
                    data = json.loads(data_str)
                    print(f"Parsed: {json.dumps(data, indent=2)}")
                    print(f"Keys in tools[0]: {list(data.get('tools', [{}])[0].keys())}")
                except Exception as e:
                    print(f"Parse error: {e}")


if __name__ == "__main__":
    test_sse_stream()
