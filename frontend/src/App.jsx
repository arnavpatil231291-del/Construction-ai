import { useState } from "react";

const TABS = [
  { k: "safety", l: "Site Safety", img: true },
  { k: "crack", l: "Crack Analysis", img: true },
  { k: "valuation", l: "Valuation", f: ["location", "area_sqft", "bedrooms", "age_years", "condition"] },
  { k: "planning", l: "Planning", f: ["project_type", "total_area_sqft", "floors", "location", "budget", "timeline_weeks"] },
  { k: "assistant", l: "Site Assistant" },
  { k: "weather", l: "Weather Advisory", f: ["location", "conditions"] },
  { k: "knowledge", l: "Knowledge" },
];

function Val({ v }) {
  if (Array.isArray(v)) {
    if (!v.length) return <em>none</em>;
    if (typeof v[0] === "object") {
      const cols = Object.keys(v[0]);
      return (
        <table>
          <thead><tr>{cols.map(c => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>{v.map((r, i) => <tr key={i}>{cols.map(c => <td key={c}>{String(r[c] ?? "")}</td>)}</tr>)}</tbody>
        </table>
      );
    }
    return <ul>{v.map((x, i) => <li key={i}>{String(x)}</li>)}</ul>;
  }
  if (v && typeof v === "object")
    return <dl>{Object.entries(v).map(([k, x]) => <div key={k}><dt>{k.replace(/_/g, " ")}</dt><dd><Val v={x} /></dd></div>)}</dl>;
  return <span>{String(v)}</span>;
}

function Plan({ rooms }) {
  let x = 0, y = 0, rowH = 0;
  const s = 8, maxW = 600;
  const boxes = (rooms || []).filter(r => r.width > 0 && r.length > 0).map(r => {
    const w = r.width * s, h = r.length * s;
    if (x + w > maxW) { x = 0; y += rowH + 6; rowH = 0; }
    const b = { ...r, x, y, w, h };
    x += w + 6; rowH = Math.max(rowH, h);
    return b;
  });
  if (!boxes.length) return null;
  return (
    <svg viewBox={`0 0 ${maxW} ${y + rowH + 4}`} style={{ width: "100%", background: "#fafafa" }}>
      {boxes.map((b, i) => (
        <g key={i}>
          <rect x={b.x} y={b.y} width={b.w} height={b.h} fill="#fde7d0" stroke="#e8710a" />
          <text x={b.x + 4} y={b.y + 14} fontSize="11">{b.name} {b.width}x{b.length}</text>
        </g>
      ))}
    </svg>
  );
}

export default function App() {
  const [tab, setTab] = useState(TABS[0]);
  const [text, setText] = useState("");
  const [fields, setFields] = useState({});
  const [file, setFile] = useState(null);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const pick = t => { setTab(t); setRes(null); setErr(""); setFile(null); setFields({}); };

  const run = async () => {
    setBusy(true); setErr(""); setRes(null);
    const fd = new FormData();
    fd.append("text", text);
    fd.append("data", JSON.stringify(fields));
    if (file) fd.append("image", file);
    try {
      const r = await fetch("/api/" + tab.k, { method: "POST", body: fd });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.detail || "Request failed (" + r.status + ")");
      setRes(j);
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  return (
    <main>
      <h2>Construction Intelligence Platform</h2>
      <nav>{TABS.map(t => <button key={t.k} className={t.k === tab.k ? "on" : ""} onClick={() => pick(t)}>{t.l}</button>)}</nav>
      <div className="card">
        {tab.img && (
          <>
            <label>Site image (JPEG/PNG/WebP, max 5 MB)</label>
            <input type="file" accept="image/*" onChange={e => setFile(e.target.files[0] || null)} />
            {file && <img className="pv" src={URL.createObjectURL(file)} alt="preview" />}
          </>
        )}
        {(tab.f || []).map(f => (
          <div key={f}>
            <label>{f.replace(/_/g, " ")}</label>
            <input value={fields[f] || ""} onChange={e => setFields({ ...fields, [f]: e.target.value })} />
          </div>
        ))}
        <label>{tab.img || tab.f ? "Notes (optional)" : "Your question"}</label>
        <textarea rows={3} value={text} onChange={e => setText(e.target.value)} />
        <button className="go" disabled={busy} onClick={run}>{busy ? "Analyzing..." : "Analyze"}</button>
        {err && <div className="err">{err}</div>}
      </div>
      {res && (
        <div className="card">
          {tab.k === "planning" && <Plan rooms={res.rooms} />}
          <Val v={res} />
        </div>
      )}
    </main>
  );
}
