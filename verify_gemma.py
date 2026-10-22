import os, json, requests
from dotenv import load_dotenv
load_dotenv()

BASE = "https://generativelanguage.googleapis.com/v1beta"
H = {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"}
MODEL = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")

r = requests.get(f"{BASE}/models", headers=H, params={"pageSize": 1000}, timeout=30)
print("List status:", r.status_code)
if r.ok:
    print("Gemma models:", [m["name"] for m in r.json().get("models", []) if "gemma" in m["name"]])
else:
    print(r.text)

prompt = ('Return ONLY a JSON object with keys "summary" (string) and '
          '"priority_score" (integer 1-5) for this PR title: "Fix typo in README". No markdown.')
r = requests.post(f"{BASE}/models/{MODEL}:generateContent", headers=H,
                  json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
print("Generate status:", r.status_code)
if not r.ok:
    print(r.text)
    raise SystemExit(1)

def extract_json(text, required=("summary", "priority_score")):
    """Find the LAST balanced {...} in the text that parses and has the required keys."""
    candidates = []
    depth, start, in_str, esc = 0, None, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc: esc = False
            elif ch == "\\": esc = True
            elif ch == '"': in_str = False
            continue
        if ch == '"': in_str = True
        elif ch == "{":
            if depth == 0: start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start:i + 1])
    for c in reversed(candidates):
        try:
            obj = json.loads(c)
            if all(k in obj for k in required):
                return obj
        except json.JSONDecodeError:
            continue
    return None

parts = r.json()["candidates"][0]["content"]["parts"]
text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
print("RAW LENGTH:", len(text))
print("PARSED:", extract_json(text))