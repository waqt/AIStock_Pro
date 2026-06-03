import json

with open("E:\\workspace\\AIResearch\\AIStock_Pro\\temp_lab\\step6_mock_messages.json", "r", encoding="utf-8") as f:
    data = json.load(f)

msgs = data["messages"]
print(f"Total messages: {len(msgs)}")
print()

# Show ALL assistant messages with their text content
for i, msg in enumerate(msgs):
    role = msg["role"]
    content = msg.get("content", "")
    has_tc = bool(msg.get("tool_calls"))

    if role == "assistant":
        text_len = 0
        text_preview = ""
        if isinstance(content, list):
            for b in content:
                if b.get("type") == "text" and b.get("text"):
                    text_len = len(b["text"])
                    raw = b["text"]
                    try:
                        fixed = raw.encode("latin-1").decode("utf-8")
                        if any("一" <= c <= "鿿" for c in fixed[:100]):
                            raw = fixed
                    except:
                        pass
                    text_preview = raw[:200]
                    break
        elif content:
            text_len = len(str(content))
            text_preview = str(content)[:200]

        tc_info = f", tool_calls={len(msg['tool_calls'])}" if has_tc else ""
        print(f"[{i}] assistant: text={text_len} chars{tc_info}")
        if text_preview:
            print(f"    Preview: {text_preview}...")
        print()

# Also check what the final raw file has
with open("E:\\workspace\\AIResearch\\AIStock_Pro\\temp_lab\\step6_mock_raw.txt", "r", encoding="utf-8") as f:
    raw = f.read()
print(f"\nRaw file: {len(raw)} bytes")
print(f"First 200: {raw[:200]}")
print(f"Last 200: {raw[-200:]}")
