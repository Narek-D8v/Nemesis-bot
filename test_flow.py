import sys, json

text = "+правила bold text"
cmd_lower = "+правила"
cmd_len = len(cmd_lower)
lower_idx = text.lower().find(cmd_lower)
after = text[lower_idx + cmd_len:]
content = after.lstrip()
content_start = lower_idx + cmd_len + (len(after) - len(content))
print(f"text={text!r}")
print(f"lower_idx={lower_idx}, cmd_len={cmd_len}")
print(f"after={after!r}")
print(f"content={content!r}")
print(f"content_start={content_start}")
print()

class MockEntity:
    type = "bold"
    offset = 9
    length = 4
    url = None
    user = None

entities = [MockEntity()]
end_bound = content_start + len(content)
result = []
for e in entities:
    if e.offset >= content_start and e.offset + e.length <= end_bound:
        d = {"type": str(e.type), "offset": e.offset - content_start, "length": e.length}
        result.append(d)
entities_json = json.dumps(result, ensure_ascii=False)
print(f"entities_json={entities_json!r}")
print()

data = json.loads(entities_json)
print("Parsed data:")
for d in data:
    print(f"  type={d['type']}, offset={d['offset']}, length={d['length']}")
print()

prefix = "📜 Правила чата:\n\n"
print(f"prefix len={len(prefix)}")
for d in data:
    d["offset"] += len(prefix)
    print(f"  adjusted type={d['type']}, offset={d['offset']}, length={d['length']}")
print()

full_text = prefix + content
print(f"Full text: {full_text!r}")
print(f"Full text len: {len(full_text)}")
for d in data:
    start = d["offset"]
    end = start + d["length"]
    print(f"Entity at [{start}:{end}]: {full_text[start:end]!r}")
