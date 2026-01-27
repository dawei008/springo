"""Test tool_search with various queries"""
import requests
import json

queries = [
    "strands memory",
    "strands agents memory",
    "strands long term memory",
    "aws strands memory"
]

for query in queries:
    print(f"\n{'='*60}")
    print(f"Query: '{query}'")
    print("="*60)
    response = requests.post(
        "http://127.0.0.1:8080/v1/tools/execute",
        json={"name": "tool_search", "input": {"query": query, "auto_activate": True}}
    )
    result = response.json().get("result", {})
    activated = result.get("activated_tool", {})
    print(f"Auto-activated: {activated.get('tool', 'None')}")
    print(f"Other matches:")
    for m in result.get("other_matches", [])[:3]:
        print(f"  - {m['name']}: {m['score']:.3f}")
