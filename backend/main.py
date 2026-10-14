import os, json, base64
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import httpx

load_dotenv()
PROVIDER = os.getenv("PROVIDER", "gemini").lower()  # gemini | mock | anthropic
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")  # check AI Studio for current names
MODEL = os.getenv("MODEL", "claude-sonnet-5-5")
MAX_IMG = 5 * 1024 * 1024
IMG_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

# Strict JSON contracts: example value doubles as the schema (type + shape).
FEATURES = {
    "safety": (True, "You are a construction site safety inspector. Identify hazards and PPE issues visible in the image.",
        {"summary": "", "risk_level": "low|medium|high|critical",
         "hazards": [{"hazard": "", "severity": "", "location": "", "action": ""}],
         "ppe": [{"item": "", "status": "worn|missing|unclear", "note": ""}],
         "recommendations": [""]}),
    "crack": (True, "You are a structural engineer. Classify the crack(s) in the image: type, severity, probable causes, corrective actions.",
        {"crack_type": "", "severity": "minor|moderate|severe", "causes": [""], "structural_risk": "",
         "actions": [""], "confidence": 0.0, "image_quality_note": ""}),
    "valuation": (False, "You are a real-estate valuer. Estimate value from the provided property data. State assumptions.",
        {"estimated_value": 0, "currency": "", "price_per_sqft": 0, "range_low": 0, "range_high": 0,
         "factors": [""], "assumptions": [""]}),
    "planning": (False, "You are a construction planner. Produce material estimate with costs, a task schedule, and a simple room layout (feet).",
        {"summary": "", "currency": "", "total_cost": 0,
         "materials": [{"item": "", "quantity": 0, "unit": "", "unit_cost": 0, "cost": 0}],
         "schedule": [{"task": "", "start_week": 0, "duration_weeks": 0}],
         "rooms": [{"name": "", "width": 0, "length": 0}]}),
    "assistant": (False, "You are a daily construction site assistant. Give practical, concise help.",
        {"answer": "", "action_items": [""]}),
    "weather": (False, "You are a construction weather advisor. Use the location/conditions given (no live data is available) to advise on site work.",
        {"summary": "", "go_no_go": "go|caution|no-go", "work_advice": [""], "risks": [""]}),
    "knowledge": (False, "You are a construction knowledge assistant (codes, materials, methods). Be accurate; say when unsure.",
        {"answer": "", "key_points": [""], "references": [""]}),
}

def conform(schema, data):
    """Force data into the schema's shape so the UI never breaks."""
    if isinstance(schema, dict):
        data = data if isinstance(data, dict) else {}
        return {k: conform(v, data.get(k)) for k, v in schema.items()}
    if isinstance(schema, list):
        return [conform(schema[0], x) for x in data] if isinstance(data, list) else []
    if isinstance(schema, bool):
        return bool(data)
    if isinstance(schema, (int, float)):
        return data if isinstance(data, (int, float)) and not isinstance(data, bool) else 0
    return "" if data is None else (data if isinstance(data, str) else str(data))

def parse_json(text):
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a:
        raise ValueError("no JSON found")
    return json.loads(text[a:b + 1])

MOCKS = {
    "safety": {"summary": "MOCK DATA: Worker near an open edge without fall protection.", "risk_level": "high",
        "hazards": [{"hazard": "Unprotected edge", "severity": "high", "location": "Upper slab", "action": "Install guardrails"}],
        "ppe": [{"item": "Hard hat", "status": "worn", "note": ""}, {"item": "Safety harness", "status": "missing", "note": "Required at height"}],
        "recommendations": ["Stop work at the edge until guardrails are fitted", "Run a PPE toolbox talk"]},
    "crack": {"crack_type": "Diagonal shear crack (MOCK)", "severity": "moderate", "causes": ["Differential settlement", "Overloading"],
        "structural_risk": "Possible loss of shear capacity if it widens", "actions": ["Install crack gauges", "Get an engineer to inspect", "Seal after cause is fixed"],
        "confidence": 0.7, "image_quality_note": "Mock response"},
    "valuation": {"estimated_value": 6500000, "currency": "INR", "price_per_sqft": 5200, "range_low": 6000000, "range_high": 7000000,
        "factors": ["Location", "Age and condition"], "assumptions": ["MOCK DATA, not a real valuation"]},
    "planning": {"summary": "MOCK DATA: Small two-bedroom house.", "currency": "INR", "total_cost": 2400000,
        "materials": [{"item": "Cement", "quantity": 400, "unit": "bags", "unit_cost": 400, "cost": 160000},
                      {"item": "Steel", "quantity": 3, "unit": "tonnes", "unit_cost": 60000, "cost": 180000}],
        "schedule": [{"task": "Foundation", "start_week": 0, "duration_weeks": 3}, {"task": "Structure", "start_week": 3, "duration_weeks": 8},
                     {"task": "Finishing", "start_week": 11, "duration_weeks": 6}],
        "rooms": [{"name": "Living", "width": 16, "length": 14}, {"name": "Bedroom 1", "width": 12, "length": 12},
                  {"name": "Bedroom 2", "width": 11, "length": 12}, {"name": "Kitchen", "width": 10, "length": 9}]},
    "assistant": {"answer": "MOCK DATA: Start with a safety briefing, then check material deliveries.", "action_items": ["Toolbox talk", "Check deliveries"]},
    "weather": {"summary": "MOCK DATA: Rain expected.", "go_no_go": "caution", "work_advice": ["Cover cement", "Delay concrete pours"], "risks": ["Slippery surfaces"]},
    "knowledge": {"answer": "MOCK DATA: M20 concrete is a common mix for residential work.", "key_points": ["Mix ratio 1:1.5:3"], "references": ["IS 456"]},
}

def _gemini(sys, text, image):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise HTTPException(500, "GEMINI_API_KEY is not set on the server")
    parts = []
    if image:
        parts.append({"inlineData": {"mimeType": image[0], "data": base64.b64encode(image[1]).decode()}})
    parts.append({"text": text or "Analyze."})
    body = {"systemInstruction": {"parts": [{"text": sys}]}, "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 2000}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    r = httpx.post(url, headers={"x-goog-api-key": key}, json=body, timeout=60)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def _claude(sys, text, image):
    import anthropic  # optional: only needed when PROVIDER=anthropic
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(500, "ANTHROPIC_API_KEY is not set on the server")
    content = []
    if image:
        content.append({"type": "image", "source": {"type": "base64", "media_type": image[0],
                                                    "data": base64.b64encode(image[1]).decode()}})
    content.append({"type": "text", "text": text or "Analyze."})
    r = anthropic.Anthropic(api_key=key).messages.create(
        model=MODEL, max_tokens=2000, system=sys, messages=[{"role": "user", "content": content}])
    return "".join(b.text for b in r.content if b.type == "text")

def call_llm(feature, system, schema, text, image=None):
    if PROVIDER == "mock":
        return conform(schema, MOCKS[feature])
    sys = (system + " Respond with ONLY one JSON object, no prose or code fences, matching exactly this shape "
           "(example values show types): " + json.dumps(schema) +
           ". If the input is unclear or incomplete, still return the JSON and explain limits in text fields.")
    try:
        raw = (_claude if PROVIDER == "anthropic" else _gemini)(sys, text, image)
        out = parse_json(raw)
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            raise HTTPException(429, "AI rate limit reached. Wait a minute and retry.")
        raise HTTPException(502, f"AI service error (HTTP {e.response.status_code}). Check your API key and model name.")
    except (ValueError, KeyError, IndexError, json.JSONDecodeError):
        raise HTTPException(502, "AI returned an unreadable response. Please retry.")
    except Exception as e:
        raise HTTPException(502, f"AI service error: {type(e).__name__}")
    return conform(schema, out)

app = FastAPI(title="Construction Intelligence Platform")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/health")
def health():
    return {"status": "ok", "provider": PROVIDER}

@app.post("/api/{feature}")
def analyze(feature: str, text: str = Form(""), data: str = Form("{}"),
            image: Optional[UploadFile] = File(None)):
    if feature not in FEATURES:
        raise HTTPException(404, "Unknown feature")
    needs_img, system, schema = FEATURES[feature]
    img = None
    if image is not None and image.filename:
        if image.content_type not in IMG_TYPES:
            raise HTTPException(400, "Unsupported image type (use JPEG, PNG, WebP or GIF)")
        raw = image.file.read()
        if not raw:
            raise HTTPException(400, "Image file is empty")
        if len(raw) > MAX_IMG:
            raise HTTPException(400, "Image too large (max 5 MB)")
        img = (image.content_type, raw)
    if needs_img and not img:
        raise HTTPException(400, "This feature requires an image")
    try:
        fields = json.loads(data) if data else {}
        fields = {k: v for k, v in fields.items() if str(v).strip()} if isinstance(fields, dict) else {}
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid structured data")
    if not img and not text.strip() and not fields:
        raise HTTPException(400, "Provide some input")
    prompt = text.strip() + ("\nProject data: " + json.dumps(fields) if fields else "")
    return call_llm(feature, system, schema, prompt, img)

from fastapi.staticfiles import StaticFiles
dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(dist):
    app.mount("/", StaticFiles(directory=dist, html=True), name="web")
