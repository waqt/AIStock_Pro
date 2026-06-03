"""Check the saved mock result messages"""
import json

with open("E:\\workspace\\AIResearch\\AIStock_Pro\\temp_lab\\step6_mock_messages.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print("Total messages:", len(data["messages"]))
print("Tool calls:", data["tool_calls_count"])
print("Rounds:", data["total_rounds"])
print()

# Find the final assistant response
for msg in data["messages"]:
    if msg["role"] == "assistant" and isinstance(msg.get("content"), list):
        for block in msg["content"]:
            if block["type"] == "text" and len(block.get("text", "")) > 500:
                text = block["text"]
                # fix mojibake
                try:
                    fixed = text.encode("latin-1").decode("utf-8")
                    if any("一" <= c <= "鿿" for c in fixed[:100]):
                        text = fixed
                except:
                    pass
                print("Final response length:", len(text), "chars")
                print("\nLast 800 chars:")
                print(text[-800:])

                # Check if JSON is complete
                if text.strip().endswith("}"):
                    print("\n✅ JSON appears complete (ends with '}')")
                else:
                    print(f"\n⚠️ JSON may be truncated. Ends with: {text[-50:]}")
                break
