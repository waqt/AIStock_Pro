import json

with open("E:\\workspace\\AIResearch\\AIStock_Pro\\temp_lab\\step6_mock_messages.json", "r", encoding="utf-8") as f:
    data = json.load(f)

msgs = data["messages"]
print(f"Total messages: {len(msgs)}, tool calls: {data['tool_calls_count']}, rounds: {data['total_rounds']}")
print()

# Print last 5 message roles
for i, msg in enumerate(msgs[-5:]):
    idx = len(msgs) - 5 + i
    role = msg["role"]
    content = msg.get("content", "")
    if isinstance(content, list):
        types = [b.get("type", "?") for b in content]
        print(f"  [{idx}] role={role}, content_type={types}")
        for b in content:
            if b.get("type") == "text" and b.get("text"):
                text = b["text"]
                try:
                    fixed = text.encode("latin-1").decode("utf-8")
                    if any("一" <= c <= "鿿" for c in fixed[:100]):
                        text = fixed
                except:
                    pass
                print(f"         text length={len(text)}, ends with: ...{text[-100:]}")
    else:
        content_str = str(content)[:200]
        print(f"  [{idx}] role={role}, content={content_str}")
