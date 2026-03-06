import { useState, useRef } from "react";
import "./Clinictrialmatch.css";

/* ─── Hardcoded patient database ─────────────────────────────────────── */
const PATIENT_DB = {
  diabetes: [
    {
      id: "P-0041",
      name: "Arjun Mehta",
      age: 52,
      gender: "Male",
      city: "Pune, MH",
      distance: "4.2 km",
      phone: "+91 98201 43762",
      score: 96,
      conditions: ["Type 2 Diabetes Mellitus", "Hypertension"],
      labs: { HbA1c: "8.4%", BMI: "29.1", eGFR: "74", Fasting_Glucose: "148 mg/dL" },
      medications: ["Metformin 500mg", "Amlodipine 5mg"],
      reasons: [
        "HbA1c 8.4% — within trial range 7–10%",
        "Age 52 — within eligibility window 30–65",
        "No prior insulin use — meets exclusion rule",
        "eGFR 74 — above minimum threshold of 45",
        "T2DM diagnosis >6 months — confirmed",
      ],
      matched_phase: "Phase 3",
      status: "Eligible",
    },
    {
      id: "P-0057",
      name: "Sunita Rao",
      age: 47,
      gender: "Female",
      city: "Mumbai, MH",
      distance: "11.8 km",
      phone: "+91 90041 22198",
      score: 91,
      conditions: ["Type 2 Diabetes Mellitus", "Dyslipidemia"],
      labs: { HbA1c: "7.9%", BMI: "27.4", eGFR: "81", Fasting_Glucose: "139 mg/dL" },
      medications: ["Glipizide 5mg", "Atorvastatin 10mg"],
      reasons: [
        "HbA1c 7.9% — optimal range for trial",
        "Age 47 — strong eligibility fit",
        "Fasting Glucose 139 — controlled, within range",
        "No cardiovascular disease history",
        "BMI 27.4 — within acceptable range",
      ],
      matched_phase: "Phase 3",
      status: "Eligible",
    },
    {
      id: "P-0083",
      name: "Rajesh Nair",
      age: 61,
      gender: "Male",
      city: "Thane, MH",
      distance: "18.5 km",
      phone: "+91 87652 09341",
      score: 84,
      conditions: ["Type 2 Diabetes Mellitus", "Mild CKD"],
      labs: { HbA1c: "9.1%", BMI: "31.2", eGFR: "52", Fasting_Glucose: "167 mg/dL" },
      medications: ["Metformin 1g", "Sitagliptin 50mg"],
      reasons: [
        "HbA1c 9.1% — within range, borderline high",
        "eGFR 52 — above exclusion threshold ≥45",
        "Age 61 — approaching upper bound",
        "No active CVD — passes key exclusion",
      ],
      matched_phase: "Phase 3",
      status: "Possible",
    },
    {
      id: "P-0102",
      name: "Priya Sharma",
      age: 39,
      gender: "Female",
      city: "Nashik, MH",
      distance: "28.3 km",
      phone: "+91 91234 56789",
      score: 78,
      conditions: ["Type 2 Diabetes Mellitus"],
      labs: { HbA1c: "7.2%", BMI: "24.8", eGFR: "88", Fasting_Glucose: "122 mg/dL" },
      medications: ["Metformin 500mg"],
      reasons: [
        "HbA1c 7.2% — within range, well-controlled",
        "Age 39 — well within eligibility",
        "Low BMI — may need diet assessment",
        "Only on Metformin — no complex interactions",
      ],
      matched_phase: "Phase 2",
      status: "Possible",
    },
  ],
  hypertension: [
    {
      id: "P-0019",
      name: "Vikram Desai",
      age: 55,
      gender: "Male",
      city: "Pune, MH",
      distance: "6.1 km",
      phone: "+91 99870 34512",
      score: 94,
      conditions: ["Stage 2 Hypertension", "Obesity"],
      labs: { SBP: "158 mmHg", DBP: "98 mmHg", BMI: "33.4", Creatinine: "1.1 mg/dL" },
      medications: ["Amlodipine 10mg", "Losartan 50mg"],
      reasons: [
        "BP 158/98 — within trial target range",
        "On 2 antihypertensives — meets inclusion",
        "No secondary hypertension cause",
        "Age 55 — ideal trial demographic",
        "Creatinine 1.1 — renal function acceptable",
      ],
      matched_phase: "Phase 3",
      status: "Eligible",
    },
    {
      id: "P-0034",
      name: "Anita Kulkarni",
      age: 49,
      gender: "Female",
      city: "Mumbai, MH",
      distance: "14.2 km",
      phone: "+91 88990 12345",
      score: 87,
      conditions: ["Stage 1 Hypertension", "Hypothyroidism"],
      labs: { SBP: "148 mmHg", DBP: "92 mmHg", BMI: "26.8", Creatinine: "0.9 mg/dL" },
      medications: ["Telmisartan 40mg", "Levothyroxine 50mcg"],
      reasons: [
        "BP 148/92 — Stage 1, meets inclusion criteria",
        "Thyroid controlled — no interaction risk",
        "No prior stroke or MI history",
        "Age 49 — strong demographic match",
      ],
      matched_phase: "Phase 2",
      status: "Eligible",
    },
  ],
  cancer: [
    {
      id: "P-0071",
      name: "Sanjay Patil",
      age: 58,
      gender: "Male",
      city: "Pune, MH",
      distance: "9.3 km",
      phone: "+91 97600 88123",
      score: 89,
      conditions: ["Stage II Colorectal Cancer", "Post-Surgery"],
      labs: { CEA: "3.2 ng/mL", Hemoglobin: "11.4 g/dL", WBC: "5.8 K/uL", Platelets: "210 K/uL" },
      medications: ["Capecitabine 1250mg", "Folic Acid"],
      reasons: [
        "Stage II CRC — matches trial criteria",
        "Post-resection ≥4 weeks — eligible",
        "CEA 3.2 — within acceptable range",
        "Performance status ECOG 1 — suitable",
        "No prior immunotherapy",
      ],
      matched_phase: "Phase 2",
      status: "Eligible",
    },
    {
      id: "P-0089",
      name: "Meera Joshi",
      age: 44,
      gender: "Female",
      city: "Navi Mumbai, MH",
      distance: "22.7 km",
      phone: "+91 86543 21098",
      score: 81,
      conditions: ["Stage IIIA Breast Cancer", "HER2+"],
      labs: { CA125: "28 U/mL", Hemoglobin: "10.8 g/dL", WBC: "4.2 K/uL", Platelets: "185 K/uL" },
      medications: ["Trastuzumab", "Paclitaxel"],
      reasons: [
        "HER2+ confirmed — matches targeted trial",
        "Stage IIIA — within inclusion window",
        "Currently on first-line HER2 therapy",
        "No bone metastasis detected",
      ],
      matched_phase: "Phase 1b",
      status: "Possible",
    },
  ],
  obesity: [
    {
      id: "P-0028",
      name: "Rahul Gupta",
      age: 36,
      gender: "Male",
      city: "Pune, MH",
      distance: "3.5 km",
      phone: "+91 93456 78901",
      score: 93,
      conditions: ["Class II Obesity", "Metabolic Syndrome"],
      labs: { BMI: "38.2", Fasting_Glucose: "108 mg/dL", Triglycerides: "210 mg/dL", HDL: "34 mg/dL" },
      medications: ["Orlistat 120mg"],
      reasons: [
        "BMI 38.2 — within trial range 35–45",
        "Metabolic syndrome confirmed",
        "Age 36 — optimal demographic",
        "Triglycerides elevated — key secondary endpoint",
        "No prior bariatric surgery",
      ],
      matched_phase: "Phase 3",
      status: "Eligible",
    },
  ],
};

const SUGGESTIONS = ["diabetes", "hypertension", "cancer", "obesity", "alzheimer's", "asthma", "arthritis", "parkinson's"];

const STATUS_CONFIG = {
  Eligible: { color: "#10b981", bg: "rgba(16,185,129,.1)", border: "rgba(16,185,129,.25)" },
  Possible: { color: "#f59e0b", bg: "rgba(245,158,11,.1)", border: "rgba(245,158,11,.25)" },
  "Not Eligible": { color: "#ef4444", bg: "rgba(239,68,68,.1)", border: "rgba(239,68,68,.25)" },
};

/* ─── Score Ring ─────────────────────────────────────────────────────── */
function ScoreRing({ score }) {
  const r = 28, c = 2 * Math.PI * r;
  const fill = (score / 100) * c;
  const color = score >= 90 ? "#10b981" : score >= 75 ? "#0ea5e9" : "#f59e0b";
  return (
    <div className="score-ring-wrap">
      <svg viewBox="0 0 72 72" width="72" height="72">
        <circle cx="36" cy="36" r={r} fill="none" stroke="rgba(255,255,255,.06)" strokeWidth="5"/>
        <circle cx="36" cy="36" r={r} fill="none" stroke={color} strokeWidth="5"
          strokeDasharray={`${fill} ${c}`} strokeLinecap="round"
          transform="rotate(-90 36 36)" className="score-arc"/>
        <text x="36" y="39" textAnchor="middle" fontSize="14" fontWeight="800"
          fill={color} fontFamily="Syne, sans-serif">{score}</text>
      </svg>
      <span className="score-label">score</span>
    </div>
  );
}

/* ─── Patient Card ───────────────────────────────────────────────────── */
function PatientCard({ patient, rank, expanded, onToggle }) {
  const st = STATUS_CONFIG[patient.status];
  return (
    <div className={`pc ${expanded ? "pc--open" : ""}`} style={{ animationDelay: `${rank * 70}ms` }}>
      {/* Rank badge */}
      <div className={`pc-rank ${rank === 0 ? "pc-rank--gold" : rank === 1 ? "pc-rank--silver" : "pc-rank--bronze"}`}>
        #{rank + 1}
      </div>

      {/* Header row */}
      <div className="pc-header" onClick={onToggle} role="button" tabIndex={0} onKeyDown={e => e.key === "Enter" && onToggle()}>
        <ScoreRing score={patient.score} />

        <div className="pc-identity">
          <div className="pc-name-row">
            <span className="pc-name">{patient.name}</span>
            <span className="pc-id">{patient.id}</span>
          </div>
          <div className="pc-meta">
            <span>{patient.age}y · {patient.gender}</span>
            <span className="pc-dot">·</span>
            <span>📍 {patient.city}</span>
            <span className="pc-dot">·</span>
            <span className="pc-dist">{patient.distance} away</span>
          </div>
          <div className="pc-conditions">
            {patient.conditions.map(c => <span key={c} className="pc-condition-tag">{c}</span>)}
          </div>
        </div>

        <div className="pc-right">
          <span className="pc-status-badge" style={{ color: st.color, background: st.bg, border: `1px solid ${st.border}` }}>
            {patient.status}
          </span>
          <span className="pc-phase">{patient.matched_phase}</span>
          <div className={`pc-chevron ${expanded ? "pc-chevron--open" : ""}`}>
            <svg viewBox="0 0 16 16" fill="none" width="16">
              <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
            </svg>
          </div>
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="pc-detail">
          <div className="pc-detail-grid">

            {/* Why matched */}
            <div className="pc-section">
              <div className="pc-section-title">
                <svg viewBox="0 0 14 14" fill="none" width="12"><path d="M7 1v6M7 9v2" stroke="#0ea5e9" strokeWidth="2" strokeLinecap="round"/><circle cx="7" cy="7" r="6" stroke="#0ea5e9" strokeWidth="1.2"/></svg>
                Why Best Suited
              </div>
              <ul className="pc-reasons">
                {patient.reasons.map((r, i) => (
                  <li key={i} className="pc-reason">
                    <span className="reason-check">✓</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Labs */}
            <div className="pc-section">
              <div className="pc-section-title">
                <svg viewBox="0 0 14 14" fill="none" width="12"><rect x="4" y="1" width="6" height="12" rx="1.5" stroke="#0ea5e9" strokeWidth="1.2"/><path d="M4 8h6" stroke="#0ea5e9" strokeWidth="1"/></svg>
                Lab Values
              </div>
              <div className="pc-labs">
                {Object.entries(patient.labs).map(([k, v]) => (
                  <div key={k} className="pc-lab-row">
                    <span className="lab-key">{k.replace(/_/g, " ")}</span>
                    <span className="lab-val">{v}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Medications */}
            <div className="pc-section">
              <div className="pc-section-title">
                <svg viewBox="0 0 14 14" fill="none" width="12"><rect x="2" y="5" width="10" height="6" rx="1.5" stroke="#0ea5e9" strokeWidth="1.2"/><path d="M5 5V3.5a2 2 0 014 0V5" stroke="#0ea5e9" strokeWidth="1.2"/></svg>
                Current Medications
              </div>
              <div className="pc-meds">
                {patient.medications.map(m => <span key={m} className="pc-med-chip">{m}</span>)}
              </div>
            </div>

            {/* Contact */}
            <div className="pc-section">
              <div className="pc-section-title">
                <svg viewBox="0 0 14 14" fill="none" width="12"><path d="M2 3a1 1 0 011-1h2l1 3-1.5 1.5a9 9 0 004 4L10 9l3 1v2a1 1 0 01-1 1A11 11 0 012 3z" stroke="#0ea5e9" strokeWidth="1.2"/></svg>
                Contact & Location
              </div>
              <div className="pc-contact">
                <div className="contact-row">
                  <span className="contact-icon">📞</span>
                  <span className="contact-val">{patient.phone}</span>
                  <button className="contact-copy" onClick={() => navigator.clipboard?.writeText(patient.phone)}>Copy</button>
                </div>
                <div className="contact-row">
                  <span className="contact-icon">📍</span>
                  <span className="contact-val">{patient.city} · {patient.distance} from clinic</span>
                </div>
              </div>
            </div>
          </div>

          <div className="pc-actions">
            <button className="pc-btn pc-btn--primary">
              <svg viewBox="0 0 14 14" fill="none" width="13"><path d="M2 3a1 1 0 011-1h2l1 3-1.5 1.5a9 9 0 004 4L10 9l3 1v2a1 1 0 01-1 1A11 11 0 012 3z" stroke="currentColor" strokeWidth="1.5"/></svg>
              Contact Patient
            </button>
            <button className="pc-btn pc-btn--secondary">
              <svg viewBox="0 0 14 14" fill="none" width="13"><path d="M7 1v6M4 4l3-3 3 3M2 10h10v2H2z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
              Export Profile
            </button>
            <button className="pc-btn pc-btn--ghost">View Full Report</button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Main page ──────────────────────────────────────────────────────── */
export default function ClinicTrialMatch() {
  const [query, setQuery] = useState("");
  const [searched, setSearched] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(null);
  const [filterStatus, setFilterStatus] = useState("All");
  const inputRef = useRef(null);

  const handleSearch = async (q = query) => {
    const key = q.trim().toLowerCase();
    if (!key) return;
    setLoading(true);
    setResults(null);
    setExpanded(null);
    setSearched(q.trim());
    await new Promise(r => setTimeout(r, 1400));
    const found = Object.entries(PATIENT_DB).find(([k]) => key.includes(k) || k.includes(key));
    setResults(found ? found[1] : []);
    setLoading(false);
  };

  const displayed = results
    ? (filterStatus === "All" ? results : results.filter(p => p.status === filterStatus))
    : null;

  const handleSuggestion = (s) => {
    setQuery(s);
    handleSearch(s);
  };

  return (
    <div className="ct-page">
      <div className="ct-bg-glow" aria-hidden />

      <main className="ct-main">

        {/* ── Header ── */}
        <div className="ct-header">
          <div className="ct-eyebrow">
            <span className="ct-eyebrow-dot" />
            Clinic Portal · Trial Candidate Finder
          </div>
          <h1 className="ct-h1">Find the best-suited<br /><em>patients for your trial</em></h1>
          <p className="ct-sub">Enter a condition or disease area and we'll surface top-matched patients ranked by eligibility score, proximity, and clinical fit.</p>
        </div>

        {/* ── Search ── */}
        <div className="ct-search-wrap">
          <div className={`ct-search-box ${loading ? "ct-search-box--loading" : ""}`}>
            <div className="ct-search-icon">
              {loading
                ? <span className="ct-spinner" />
                : <svg viewBox="0 0 20 20" fill="none" width="18"><circle cx="9" cy="9" r="6" stroke="#0ea5e9" strokeWidth="1.8"/><path d="M15 15l3 3" stroke="#0ea5e9" strokeWidth="2" strokeLinecap="round"/></svg>
              }
            </div>
            <input
              ref={inputRef}
              className="ct-search-input"
              placeholder="e.g. diabetes, hypertension, cancer…"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSearch()}
              autoComplete="off"
              spellCheck="false"
            />
            {query && (
              <button className="ct-search-clear" onClick={() => { setQuery(""); setResults(null); setSearched(""); inputRef.current?.focus(); }}>
                <svg viewBox="0 0 12 12" fill="none" width="12"><path d="M1 1l10 10M11 1L1 11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>
              </button>
            )}
            <button className="ct-search-btn" onClick={() => handleSearch()} disabled={!query || loading}>
              {loading ? "Searching…" : "Find Patients"}
            </button>
          </div>

          {/* Suggestions */}
          {!results && !loading && (
            <div className="ct-suggestions">
              <span className="ct-sugg-label">Try:</span>
              {SUGGESTIONS.map(s => (
                <button key={s} className="ct-sugg-chip" onClick={() => handleSuggestion(s)}>
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* ── Loading state ── */}
        {loading && (
          <div className="ct-loading">
            <div className="ct-loading-bar"><div className="ct-loading-fill" /></div>
            <div className="ct-loading-steps">
              {["Scanning patient database…", "Running eligibility engine…", "Ranking by score & proximity…"].map((s, i) => (
                <span key={s} className="ct-loading-step" style={{ animationDelay: `${i * 0.4}s` }}>{s}</span>
              ))}
            </div>
          </div>
        )}

        {/* ── Results ── */}
        {displayed !== null && !loading && (
          <div className="ct-results">
            {/* Results header */}
            <div className="ct-results-header">
              <div className="ct-results-meta">
                <span className="ct-results-title">
                  {displayed.length > 0
                    ? <>{results.length} candidate{results.length > 1 ? "s" : ""} found for <em>"{searched}"</em></>
                    : <>No candidates found for <em>"{searched}"</em></>
                  }
                </span>
                {results.length > 0 && (
                  <span className="ct-results-sub">Ranked by eligibility score · Showing best matches first</span>
                )}
              </div>

              {results.length > 0 && (
                <div className="ct-filters">
                  {["All", "Eligible", "Possible"].map(f => (
                    <button key={f} className={`ct-filter-btn ${filterStatus === f ? "ct-filter-btn--active" : ""}`}
                      onClick={() => setFilterStatus(f)}>
                      {f}
                      <span className="ct-filter-count">
                        {f === "All" ? results.length : results.filter(p => p.status === f).length}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Summary strip */}
            {results.length > 0 && (
              <div className="ct-summary-strip">
                {[
                  { label: "Total Matched", val: results.length, icon: "👥" },
                  { label: "Eligible", val: results.filter(p => p.status === "Eligible").length, icon: "✅" },
                  { label: "Possible", val: results.filter(p => p.status === "Possible").length, icon: "⚠️" },
                  { label: "Avg Score", val: Math.round(results.reduce((a, p) => a + p.score, 0) / results.length) + "%", icon: "📊" },
                  { label: "Top Match", val: results[0]?.name.split(" ")[0], icon: "🏆" },
                ].map(s => (
                  <div key={s.label} className="ct-strip-item">
                    <span className="strip-icon">{s.icon}</span>
                    <span className="strip-val">{s.val}</span>
                    <span className="strip-label">{s.label}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Cards */}
            <div className="ct-cards">
              {displayed.length === 0
                ? (
                  <div className="ct-empty">
                    <span className="ct-empty-icon">🔍</span>
                    <p>No patients match this filter. Try <button className="ct-empty-link" onClick={() => setFilterStatus("All")}>viewing all candidates</button>.</p>
                  </div>
                )
                : displayed.map((p, i) => (
                  <PatientCard key={p.id} patient={p} rank={i}
                    expanded={expanded === p.id}
                    onToggle={() => setExpanded(expanded === p.id ? null : p.id)}
                  />
                ))
              }
            </div>
          </div>
        )}

        {/* ── Empty state ── */}
        {!results && !loading && (
          <div className="ct-idle">
            <div className="ct-idle-visual">
              <svg viewBox="0 0 120 100" fill="none" width="120">
                <circle cx="40" cy="40" r="28" stroke="#1e3a5f" strokeWidth="1.5" strokeDasharray="4 3"/>
                <circle cx="40" cy="40" r="18" stroke="#0ea5e9" strokeWidth="1" opacity="0.4"/>
                <path d="M58 58l20 20" stroke="#0ea5e9" strokeWidth="2.5" strokeLinecap="round"/>
                <circle cx="40" cy="40" r="5" fill="#0ea5e9" opacity="0.7"/>
                <circle cx="78" cy="78" r="6" fill="none" stroke="#0ea5e9" strokeWidth="2"/>
              </svg>
            </div>
            <p className="ct-idle-text">Enter a condition above to find your best-matched trial candidates</p>
          </div>
        )}

      </main>
    </div>
  );
}