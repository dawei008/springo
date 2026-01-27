"""Test tool_search with auto_activate"""
import requests
import json

# Test tool_search
response = requests.post(
    "http://127.0.0.1:8080/v1/tools/execute",
    json={"name": "tool_search", "input": {"query": "strands memory", "auto_activate": True}}
)

result = response.json()
print(json.dumps(result, indent=2, ensure_ascii=False))
