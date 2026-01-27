"""Debug why github tool matches strands memory"""
import sys
sys.path.insert(0, '/Users/awsdawei/claude/springo')

from tool_registry import get_tool_registry, DeferredTool

# Create a test DeferredTool to debug scoring
test_tool = DeferredTool(
    name="github__create_or_update_file",
    description="Create or update a single file in a GitHub repository",
    server_name="github",
    keywords=["github", "create", "or", "update", "file"]
)

query = "strands memory"
query_lower = query.lower()
query_words = set(query_lower.split())

print(f"Query: '{query}'")
print(f"Query words: {query_words}")
print(f"Tool name: {test_tool.name}")
print(f"Keywords: {test_tool.keywords}")
print()

# Debug the matches_query function step by step
name_lower = test_tool.name.lower()
name_normalized = name_lower.replace('__', ' ').replace('-', ' ').replace('_', ' ')
name_words = set(name_normalized.split())

print(f"Name normalized: '{name_normalized}'")
print(f"Name words: {name_words}")
print()

# Check name matching
print("Checking name matches:")
for w in query_words:
    in_normalized = w in name_normalized
    in_any_word = any(w in nw for nw in name_words)
    print(f"  '{w}': in_normalized={in_normalized}, in_any_word={in_any_word}")

# Check keyword matching
print("\nChecking keyword matches:")
for kw in test_tool.keywords:
    kw_lower = kw.lower()
    match1 = query_lower in kw_lower
    match2 = kw_lower in query_lower
    print(f"  '{kw}': query_in_kw={match1}, kw_in_query={match2}")
    for qw in query_words:
        if qw in kw_lower:
            print(f"    -> '{qw}' found in '{kw_lower}'!")

# Check description matching
desc_lower = test_tool.description.lower()
print(f"\nDescription: '{desc_lower}'")
print("Checking description matches:")
for w in query_words:
    found = w in desc_lower
    print(f"  '{w}': found={found}")

# Now call the actual function
score = test_tool.matches_query(query)
print(f"\nFinal score: {score}")
