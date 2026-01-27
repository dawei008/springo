"""Debug tool_search - search without auto_activate to see raw results"""
import requests
import json

# Test 1: Search without auto_activate
print("=" * 60)
print("Test 1: Search without auto_activate")
print("=" * 60)
response = requests.post(
    "http://127.0.0.1:8080/v1/tools/execute",
    json={"name": "tool_search", "input": {"query": "strands memory", "auto_activate": False, "max_results": 10}}
)
result = response.json()
print("Query: strands memory")
print("Results:")
for r in result.get("result", {}).get("results", []):
    print(f"  {r['name']}: score={r.get('score', 0):.3f} status={r.get('status')}")

# Test 2: Search for just "strands"
print("\n" + "=" * 60)
print("Test 2: Search for 'strands'")
print("=" * 60)
response = requests.post(
    "http://127.0.0.1:8080/v1/tools/execute",
    json={"name": "tool_search", "input": {"query": "strands", "auto_activate": False, "max_results": 10}}
)
result = response.json()
print("Query: strands")
print("Results:")
for r in result.get("result", {}).get("results", []):
    print(f"  {r['name']}: score={r.get('score', 0):.3f} status={r.get('status')}")

# Test 3: Search for "strands agents"
print("\n" + "=" * 60)
print("Test 3: Search for 'strands agents'")
print("=" * 60)
response = requests.post(
    "http://127.0.0.1:8080/v1/tools/execute",
    json={"name": "tool_search", "input": {"query": "strands agents", "auto_activate": False, "max_results": 10}}
)
result = response.json()
print("Query: strands agents")
print("Results:")
for r in result.get("result", {}).get("results", []):
    print(f"  {r['name']}: score={r.get('score', 0):.3f} status={r.get('status')}")
