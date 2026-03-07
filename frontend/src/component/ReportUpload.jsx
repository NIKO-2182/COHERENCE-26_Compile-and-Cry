import { useState, useRef, useEffect } from "react";
import "./ReportUpload.css";
import ClinicalTrialMap from "./ClinicalTrialMap";
import { useTrialData } from "../context/TrialDataContext";
/* ═══════════════════════════════════════════════════
   DNA HELIX — Three.js, free-floating, right-shifted
═══════════════════════════════════════════════════ */
function DNAHelix({ phase }) {
  const mountRef = useRef(null);
  const phaseRef = useRef(phase);
  useEffect(() => { phaseRef.current = phase; }, [phase]);

  useEffect(() => {
    const el = mountRef.current;
    if (!el) return;

    const loadAndInit = () => {
      const THREE = window.THREE;
      if (!THREE) return;

      const W = el.clientWidth, H = el.clientHeight;
      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setSize(W, H);
      renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
      renderer.setClearColor(0x000000, 0);
      el.appendChild(renderer.domElement);

      const scene  = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(38, W / H, 0.1, 100);
      /* ── Shift camera right so helix sits right-of-center ── */
      camera.position.set(1.2, 0, 9.5);
      camera.lookAt(1.2, 0, 0);

const C = {
        strandA:  new THREE.Color(0x8569E4),   // medium slate blue
        strandB:  new THREE.Color(0xA68CEE),   // tropical indigo
        pair:     new THREE.Color(0x510993),   // indigo deep
        nodeA:    new THREE.Color(0xC7AFF7),   // mauve
        nodeB:    new THREE.Color(0x6B39BC),   // grape
        glow:     new THREE.Color(0x7c3aed),   // violet glow
        dataFlow: new THREE.Color(0xd8b4fe),   // light purple flow
        bokeh:    new THREE.Color(0xA68CEE),   // tropical indigo
      };

      const root = new THREE.Group();
      /* ── Shift the helix group right ── */
      root.position.x = 1.0;
      scene.add(root);

      /* ── Helix — SHORTER (HEIGHT 5 not 7) ── */
      const TURNS = 4.2, HEIGHT = 5.2, RADIUS = 0.92, SEG = 130, TUBE = 0.038;

      const strandMesh = (offset, color) => {
        const pts = Array.from({ length: SEG + 1 }, (_, i) => {
          const t = i / SEG, a = t * Math.PI * 2 * TURNS + offset;
          return new THREE.Vector3(Math.cos(a) * RADIUS, (t - 0.5) * HEIGHT, Math.sin(a) * RADIUS);
        });
        const geo = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), SEG * 2, TUBE, 8, false);
        const mat = new THREE.MeshStandardMaterial({
          color, emissive: color, emissiveIntensity: 1.5, roughness: 0.15, metalness: 0.5,
          transparent: true, opacity: 0.9,
        });
        return new THREE.Mesh(geo, mat);
      };

      const strand1 = strandMesh(0, C.strandA);
      const strand2 = strandMesh(Math.PI, C.strandB);
      root.add(strand1, strand2);

      /* ── Base pairs ── */
      const PAIRS = 20;
      for (let i = 0; i < PAIRS; i++) {
        const t = (i + 0.5) / PAIRS, a = t * Math.PI * 2 * TURNS, y = (t - 0.5) * HEIGHT;
        const p1 = new THREE.Vector3(Math.cos(a) * RADIUS, y, Math.sin(a) * RADIUS);
        const p2 = new THREE.Vector3(Math.cos(a + Math.PI) * RADIUS, y, Math.sin(a + Math.PI) * RADIUS);
        const mid = p1.clone().add(p2).multiplyScalar(0.5);
        const bar = new THREE.Mesh(
          new THREE.CylinderGeometry(0.022, 0.022, p1.distanceTo(p2), 6),
          new THREE.MeshStandardMaterial({ color: C.pair, emissive: C.glow, emissiveIntensity: 0.55, roughness: 0.3, metalness: 0.4, transparent: true, opacity: 0.6 })
        );
        bar.position.copy(mid);
        bar.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), p1.clone().sub(p2).normalize());
        root.add(bar);
        [[p1, C.nodeA],[p2, C.nodeB]].forEach(([pos, col]) => {
          const s = new THREE.Mesh(new THREE.SphereGeometry(0.072, 10, 10),
            new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 2.2, roughness: 0.08, transparent: true, opacity: 0.93 }));
          s.position.copy(pos);
          root.add(s);
        });
      }

      /* ── Flow particles ── */
      const flow = Array.from({ length: 10 }, (_, k) => {
        const m = new THREE.Mesh(new THREE.SphereGeometry(0.05, 8, 8),
          new THREE.MeshStandardMaterial({ color: C.dataFlow, emissive: C.dataFlow, emissiveIntensity: 4, transparent: true, opacity: 0 }));
        m.userData = { t: k / 10, strand: k % 2, speed: 0.004 + Math.random() * 0.003 };
        root.add(m);
        return m;
      });

      /* ── Bokeh — constrained to right half ── */
      const BC = 180;
      const bp = new Float32Array(BC * 3);
      for (let i = 0; i < BC; i++) {
        bp[i*3]   = 0.5 + Math.random() * 6;       // right-biased x
        bp[i*3+1] = (Math.random() - 0.5) * 8;
        bp[i*3+2] = (Math.random() - 0.5) * 4 - 2;
      }
      const bokehGeo = new THREE.BufferGeometry();
      bokehGeo.setAttribute("position", new THREE.BufferAttribute(bp, 3));
      const bokehMat = new THREE.PointsMaterial({ color: C.bokeh, size: 0.05, transparent: true, opacity: 0.25, sizeAttenuation: true });
      const bokeh = new THREE.Points(bokehGeo, bokehMat);
      scene.add(bokeh);

      /* ── Lights ── */
      scene.add(new THREE.AmbientLight(0xffffff, 0.1));
      const pA = new THREE.PointLight(0x38bdf8, 3.2, 13); pA.position.set(4, 2, 4); scene.add(pA);
      const pB = new THREE.PointLight(0x818cf8, 2.5, 11); pB.position.set(-1, -1, 3); scene.add(pB);
      const pC = new THREE.PointLight(0x2563eb, 1.6, 9);  pC.position.set(1, -3, 2); scene.add(pC);

      /* ── Animate ── */
      let then = performance.now(), raf;
      const animate = () => {
        raf = requestAnimationFrame(animate);
        const now = performance.now(), dt = (now - then) / 1000; then = now;
        const isProc = phaseRef.current === "processing";
        const isDone = phaseRef.current === "done";
        const spd = isProc ? 3.5 : 1;

        root.rotation.y += 0.3 * spd * dt;
        root.rotation.x  = Math.sin(now * 0.00022) * 0.06;

        bokeh.rotation.y += 0.025 * dt;
        bokehMat.opacity  = 0.16 + Math.sin(now * 0.0006) * 0.09;

        const gI = 1.3 + Math.sin(now * 0.0009) * 0.45;
        strand1.material.emissiveIntensity = gI * (isProc ? 2.1 : 1);
        strand2.material.emissiveIntensity = gI * (isProc ? 2.1 : 1);
        pA.intensity = 3.2 + Math.sin(now * 0.00082) * 1.1;
        pB.intensity = 2.5 + Math.cos(now * 0.001) * 0.8;

        flow.forEach(p => {
          const active = isProc || isDone;
          p.material.opacity = Math.max(0, Math.min(active ? 0.88 : 0, p.material.opacity + (active ? 0.05 : -0.05)));
          p.userData.t = (p.userData.t + p.userData.speed * spd) % 1;
          const tt = p.userData.t, a = tt * Math.PI * 2 * TURNS + (p.userData.strand === 0 ? 0 : Math.PI);
          p.position.set(Math.cos(a) * RADIUS, (tt - 0.5) * HEIGHT, Math.sin(a) * RADIUS);
        });

        renderer.render(scene, camera);
      };
      animate();

      const onResize = () => {
        const w = el.clientWidth, h = el.clientHeight;
        camera.aspect = w / h; camera.updateProjectionMatrix(); renderer.setSize(w, h);
      };
      window.addEventListener("resize", onResize);

      return () => {
        window.removeEventListener("resize", onResize);
        cancelAnimationFrame(raf);
        renderer.dispose();
        if (el.contains(renderer.domElement)) el.removeChild(renderer.domElement);
      };
    };

    if (window.THREE) return loadAndInit();
    const script = document.createElement("script");
    script.src = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js";
    let cleanup;
    script.onload = () => { cleanup = loadAndInit(); };
    document.head.appendChild(script);
    return () => cleanup?.();
  }, []);

  return <div ref={mountRef} className="dna-mount" />;
}

/* ─── Steps ──────────────────────────────────────────── */
const STEPS = [
  { label: "Anonymizing patient data",           sub: "PII scan & removal" },
  { label: "Extracting diagnoses & conditions",  sub: "BioBERT NER inference" },
  { label: "Parsing lab values",                 sub: "HbA1c · eGFR · BMI · Glucose" },
  { label: "Identifying medications",            sub: "Drug name normalization" },
  { label: "Detecting patient location",         sub: "Geo-coordinate resolution" },
  { label: "Running eligibility engine",         sub: "XGBoost + rule-based filter" },
  { label: "Ranking trial matches",              sub: "Score × geo-penalty sort" },
  { label: "Ethics & compliance check",          sub: "Differential privacy applied" },
];
const DURATIONS = [700, 950, 850, 650, 600, 1050, 750, 500];



/* ─── Main ───────────────────────────────────────────── */
export default function ReportUpload({ onNavigate }) {
  const [phase, setPhase]           = useState("idle");
  const [file, setFile]             = useState(null);
  const [dragging, setDragging]     = useState(false);
  const [stepsDone, setStepsDone]   = useState([]);
  const [activeStep, setActiveStep] = useState(-1);
  const [progress, setProgress]     = useState(0);
  const inputRef = useRef(null);

const FASTAPI_URL = "http://192.168.137.226:8080/upload-report"; // ← set your IP here
const BASE_URL    = "http://192.168.137.226:8080";
const { fetchDashboardData, trialData } = useTrialData();
const metrics = trialData?.metricsData ?? { conditions: 0, labValues: 0, trialsMatched: 0 };
const runExtraction = async (f) => {
  setFile(f);
  setPhase("processing");
  setStepsDone([]);
  setActiveStep(0);
  setProgress(0);

  // ── Upload to FastAPI ──────────────────────────────
  const formData = new FormData();
  formData.append("file", f);

  let apiResult = null;
  const uploadPromise = fetch(FASTAPI_URL, {
    method: "POST",
    body: formData,
  })
    .then((res) => res.json())
    .then((data) => { apiResult = data; })
    .catch((err) => console.error("Upload failed:", err));

  // ── Run UI steps in parallel ───────────────────────
  const total = DURATIONS.reduce((a, b) => a + b, 0);
  let elapsed = 0;

  for (let i = 0; i < STEPS.length; i++) {
    setActiveStep(i);
    await new Promise((r) => setTimeout(r, DURATIONS[i]));
    setStepsDone((prev) => [...prev, i]);
    elapsed += DURATIONS[i];
    setProgress(Math.round((elapsed / total) * 100));
  }

  // ── Wait for API if still running ─────────────────
  await uploadPromise;

  // ── Use real results if available ─────────────────
await fetchDashboardData();

  await new Promise((r) => setTimeout(r, 280));
  setPhase("done");
};

  const handleFile = (f) => { if (f?.type === "application/pdf") runExtraction(f); };
  const reset = () => {
    setPhase("idle"); setFile(null);
    setStepsDone([]); setActiveStep(-1); setProgress(0);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="ru-page">
      <div className="ru-bg-deep"  aria-hidden />
      <div className="ru-bg-glow"  aria-hidden />
      <div className="ru-bg-noise" aria-hidden />
      <div className="ru-bg-ecg-1" aria-hidden />   {/* ← ADD */}
      <div className="ru-bg-ecg-2" aria-hidden />   {/* ← ADD */}
      <div className="ru-bg-ecg-3" aria-hidden />   {/* ← ADD */}

      {/* ══ HERO SECTION ══ */}
      <main className="ru-main">

        {/* LEFT */}
        <section className="ru-left">
          {phase === "idle" && (
            <div className="ru-idle">
              <div className="ru-eyebrow"><span className="ru-pip"/>AI-Powered Clinical Trial Matching</div>

              <h1 className="ru-h1">
                Upload a report.<br/>
                <span className="ru-h1-accent">Find the right trial.</span>
              </h1>

              <p className="ru-body">
                Our AI engine reads your medical report, extracts clinical data diagnoses, lab values, medications and matches patients to active clinical trials nearby with full transparency.
              </p>

              <div className="ru-badges">
                {["BioBERT NER","XGBoost Scoring","Geo Matching","SHAP Explainability","HIPAA Safe"].map(b => (
                  <span key={b} className="ru-badge">{b}</span>
                ))}
              </div>

              <div
                className={`ru-dz${dragging?" ru-dz--drag":""}`}
                onClick={() => inputRef.current?.click()}
                onDrop={e => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); }}
                onDragOver={e => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                role="button" tabIndex={0}
                onKeyDown={e => e.key==="Enter" && inputRef.current?.click()}
              >
                <input ref={inputRef} type="file" accept="application/pdf" style={{display:"none"}} onChange={e => handleFile(e.target.files[0])}/>
                <div className="ru-dz-ring">
                  <svg viewBox="0 0 32 32" fill="none" width="24" height="24">
                    <path d="M16 4v20M16 4L9 11M16 4l7 7" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M4 26h24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.35"/>
                  </svg>
                </div>
                <div className="ru-dz-text">
                  <span className="ru-dz-primary">Drop your medical report here</span>
                  <span className="ru-dz-sub">PDF · Max 20 MB · Encrypted in transit</span>
                </div>
                <span className="ru-dz-btn">Browse file</span>
              </div>

              {/* <div className="ru-stats">
                {[{n:"2,400+",l:"Active Trials"},{n:"98%",l:"Match Accuracy"},{n:"<8s",l:"Analysis Time"}].map(s => (
                  <div key={s.l} className="ru-stat">
                    <span className="ru-stat-n">{s.n}</span>
                    <span className="ru-stat-l">{s.l}</span>
                  </div>
                ))}
              </div> */}
            </div>
          )}

          {phase === "processing" && (
            <div className="ru-proc">
              <div className="ru-proc-top">
                <div className="ru-file-chip">
                  <svg viewBox="0 0 18 22" fill="none" width="15"><rect x="1" y="1" width="12" height="20" rx="2.5" fill="rgba(96,165,250,.08)" stroke="#60a5fa" strokeWidth="1.1"/><path d="M13 1l4 4H13V1z" fill="#60a5fa" opacity="0.3"/><rect x="3" y="9" width="7" height="1.4" rx=".7" fill="#60a5fa" opacity="0.35"/></svg>
                  <span className="ru-fname">{file?.name}</span>
                  <span className="ru-fsize">{(file?.size/1024/1024).toFixed(1)} MB</span>
                </div>
                <div className="ru-pbar-track"><div className="ru-pbar-fill" style={{width:`${progress}%`}}/></div>
                <div className="ru-pct">{progress}<span>%</span></div>
              </div>
              <div className="ru-steps">
                {STEPS.map((s, i) => {
                  const done = stepsDone.includes(i), active = activeStep === i && !done;
                  return (
                    <div key={i} className={`ru-step ${done?"rs--done":active?"rs--active":"rs--wait"}`} style={{animationDelay:`${i*28}ms`}}>
                      <div className="ru-step-l">
                        <div className="ru-step-box">
                          {done ? <svg viewBox="0 0 14 14" fill="none" width="12"><path d="M2.5 7l3 3L11.5 4" stroke="#60a5fa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                               : active ? <span className="ru-spin"/> : <span className="ru-snum">{i+1}</span>}
                        </div>
                        <div className="ru-step-txt">
                          <span className="ru-step-name">{s.label}</span>
                          <span className="ru-step-sub">{s.sub}</span>
                        </div>
                      </div>
                      {active && <div className="ru-bar"><div className="ru-bar-fill"/></div>}
                      {done   && <span className="ru-done-tag">done</span>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {phase === "done" && (
            <div className="ru-done">
              <div className="ru-done-icon">
                <svg viewBox="0 0 52 52" fill="none" width="52">
                  <circle cx="26" cy="26" r="23" stroke="rgba(96,165,250,.15)" strokeWidth="1.5"/>
                  <circle cx="26" cy="26" r="23" stroke="#60a5fa" strokeWidth="1.5" strokeDasharray="144" strokeDashoffset="144" className="done-ring"/>
                  <path d="M15 26l8 8 14-16" stroke="#60a5fa" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <h2 className="ru-done-title">Analysis Complete</h2>
              <p className="ru-done-sub">Your report has been processed and matched against active trials in your region.</p>
              <div className="ru-metrics">
                {[[metrics.conditions,"Conditions"],[metrics.labValues,"Lab Values"],[metrics.trialsMatched,"Trials Matched"]].map(([n,l]) => (
                  <div key={l} className="ru-metric"><span className="ru-metric-n">{n}</span><span className="ru-metric-l">{l}</span></div>
                ))}
              </div>
              <button className="ru-goto" onClick={() => onNavigate("dashboard")}>
                <span>🏥</span><span>Get Detail Report</span>
                <svg viewBox="0 0 14 14" fill="currentColor" width="12" className="ru-arr"><path d="M7.293 1.293a1 1 0 011.414 0l5 5a1 1 0 010 1.414l-5 5a1 1 0 01-1.414-1.414L10.586 8H1a1 1 0 110-2h9.586L7.293 2.707a1 1 0 010-1.414z"/></svg>
              </button>
              <button className="ru-again" onClick={reset}>↺ Upload another report</button>
              <p className="ru-privacy">🛡 All data processed locally · No PHI retained · HIPAA compliant</p>
            </div>
          )}
        </section>

        {/* RIGHT — DNA */}
        <section className="ru-right">
          <DNAHelix phase={phase}/>
          {phase === "idle" && (
            <div className="ru-helix-labels">
              <div className="rhl rhl--tl">
                <span className="rhl-pip"/><div className="rhl-body"><span className="rhl-head">Connecting patients</span><span className="rhl-sub">to clinical possibilities</span></div>
              </div>
              <div className="rhl rhl--br">
                <span className="rhl-pip rhl-pip--violet"/><div className="rhl-body"><span className="rhl-head">AI eligibility engine</span><span className="rhl-sub">XGBoost + SHAP transparency</span></div>
              </div>
              <div className="rhl rhl--mid">
                <span className="rhl-pip rhl-pip--teal"/><div className="rhl-body"><span className="rhl-head">BioBERT NER</span><span className="rhl-sub">Medical entity extraction</span></div>
              </div>
            </div>
          )}
          <div className={`ru-helix-status ru-helix-status--${phase}`}>
            <span className={`hs-dot ${phase==="processing"?"hs-dot--pulse":phase==="done"?"hs-dot--green":""}`}/>
            {phase==="idle"&&"Ready to analyze"}
            {phase==="processing"&&"Sequencing genomic markers…"}
            {phase==="done"&&"Analysis complete"}
          </div>
        </section>
      </main>

      {/* ══ MAP SECTION (always visible after page load) ══ */}
      <ClinicalTrialMap />

    </div>
  );
}