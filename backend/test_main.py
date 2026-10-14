from fastapi.testclient import TestClient
import main
c = TestClient(main.app)

def test_unknown(): assert c.post("/api/nope", data={"text": "x"}).status_code == 404
def test_image_required(): assert c.post("/api/safety", data={"text": "x"}).status_code == 400
def test_bad_type(): assert c.post("/api/crack", files={"image": ("a.txt", b"hi", "text/plain")}).status_code == 400
def test_empty_image(): assert c.post("/api/crack", files={"image": ("a.png", b"", "image/png")}).status_code == 400
def test_no_input(): assert c.post("/api/assistant").status_code == 400
def test_bad_data(): assert c.post("/api/valuation", data={"data": "{bad"}).status_code == 400
def test_conform():
    out = main.conform(main.FEATURES["crack"][2], {"severity": 5, "causes": "x", "confidence": "high"})
    assert out["severity"] == "5" and out["causes"] == [] and out["confidence"] == 0
def test_mocked(monkeypatch):
    monkeypatch.setattr(main, "call_llm", lambda *a, **k: {"answer": "ok"})
    assert c.post("/api/knowledge", data={"text": "hi"}).json() == {"answer": "ok"}

def test_mock_provider(monkeypatch):
    monkeypatch.setattr(main, "PROVIDER", "mock")
    for f in main.FEATURES:
        img = {"image": ("a.png", b"x", "image/png")} if main.FEATURES[f][0] else None
        r = c.post(f"/api/{f}", data={"text": "hi"}, files=img)
        assert r.status_code == 200 and set(r.json()) == set(main.FEATURES[f][2])
