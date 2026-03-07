/**
 * Dashboard.jsx — UPDATED
 *
 * Changes:
 *  1. HealthBot removed entirely
 *  2. Cache logic added (sessionStorage-backed, 10-min TTL)
 *  3. TrialMap replaced with MatchedTrialsMap — shows ONLY the matched trials
 *     from TrialDataContext using the Google Maps logic from ClinicalTrialMap.jsx
 *  4. "View Details" opens ClinicalTrials.gov; "Contact Researcher" opens the
 *     ContactModal from the map section
 */

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import './Dashboard.css';
import { useTrialData } from '../context/TrialDataContext';
import { GoogleMap, useJsApiLoader, Marker, InfoWindow } from '@react-google-maps/api';

/* ─── Google Maps config ──────────────────────────────── */
const GMAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
const LIBRARIES     = ['places'];
const INDIA_CENTER  = { lat: 22.9734, lng: 78.6569 };

/**
 * Build the correct trial details URL.
 * - NCT IDs (NCT followed by digits) → clinicaltrials.gov/study/NCTxxxxxxxx
 * - CTRI IDs (Indian registry CTRI/...) → ctri.nic.in
 * - Anything else → falls back to a ClinicalTrials.gov search
 */
function trialDetailsUrl(id = '') {
  if (!id) return 'https://clinicaltrials.gov';
  if (/^NCT\d+$/i.test(id.trim()))
    return `https://clinicaltrials.gov/study/${id.trim()}`;
  if (/^CTRI\//i.test(id.trim()))
    return `https://ctri.nic.in/Clinicaltrials/showallp.php?mid1=&EncHid=&userName=${encodeURIComponent(id.trim())}`;
  return `https://clinicaltrials.gov/search?term=${encodeURIComponent(id.trim())}`;
}

/* ─── Persistent cache helpers (localStorage, 24-hour TTL) ── */
const CACHE_TTL_MS = 24 * 60 * 60 * 1000;

function cacheGet(key) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const { data, ts } = JSON.parse(raw);
    if (Date.now() - ts > CACHE_TTL_MS) { localStorage.removeItem(key); return null; }
    return data;
  } catch { return null; }
}

function cacheSet(key, data) {
  try { localStorage.setItem(key, JSON.stringify({ data, ts: Date.now() })); } catch { /* quota */ }
}

/* ─── Google Maps dark style (purple palette) ─────────── */
const MAP_STYLES = [
  { elementType: 'geometry',                stylers: [{ color: '#06000f' }] },
  { elementType: 'labels.text.fill',        stylers: [{ color: '#4a3468' }] },
  { elementType: 'labels.text.stroke',      stylers: [{ color: '#03000a' }] },
  { featureType: 'administrative',          elementType: 'geometry',         stylers: [{ color: '#0e0224' }] },
  { featureType: 'administrative.country',  elementType: 'labels.text.fill', stylers: [{ color: '#6b4f94' }] },
  { featureType: 'administrative.locality', elementType: 'labels.text.fill', stylers: [{ color: '#6b4f94' }] },
  { featureType: 'poi',                     elementType: 'labels.text.fill', stylers: [{ color: '#4a3468' }] },
  { featureType: 'poi.park',                elementType: 'geometry',         stylers: [{ color: '#080014' }] },
  { featureType: 'road',                    elementType: 'geometry',         stylers: [{ color: '#12022e' }] },
  { featureType: 'road',                    elementType: 'geometry.stroke',  stylers: [{ color: '#08001a' }] },
  { featureType: 'road',                    elementType: 'labels.text.fill', stylers: [{ color: '#3d2260' }] },
  { featureType: 'road.highway',            elementType: 'geometry',         stylers: [{ color: '#1a0535' }] },
  { featureType: 'road.highway',            elementType: 'labels.text.fill', stylers: [{ color: '#6b39bc' }] },
  { featureType: 'transit',                 elementType: 'geometry',         stylers: [{ color: '#080014' }] },
  { featureType: 'water',                   elementType: 'geometry',         stylers: [{ color: '#03000a' }] },
  { featureType: 'water',                   elementType: 'labels.text.fill', stylers: [{ color: '#2d0a5e' }] },
];

/* ─── Phase colours (matches ClinicalTrialMap) ────────── */
const PHASE_COLOR = {
  'Phase I':       '#f59e0b',
  'Phase I/II':    '#f97316',
  'Phase II':      '#0ea5e9',
  'Phase III':     '#10b981',
  'Phase IV':      '#6366f1',
  'Observational': '#8b5cf6',
};

/* ─── Marker SVG icons ────────────────────────────────── */
function markerIcon(color = '#A68CEE', size = 34) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size + 6}" viewBox="0 0 34 40">
    <circle cx="17" cy="17" r="15" fill="${color}" fill-opacity="0.16" stroke="${color}" stroke-width="1.4"/>
    <circle cx="17" cy="17" r="7" fill="${color}"/>
    <line x1="17" y1="32" x2="17" y2="39" stroke="${color}" stroke-width="2" stroke-linecap="round"/>
  </svg>`;
  return {
    url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
    scaledSize: { width: size, height: size + 6 },
    anchor: { x: size / 2, y: size + 6 },
  };
}

/* ─── Contact Modal ───────────────────────────────────── */
function ContactModal({ trial, onClose }) {
  const [name,    setName]    = useState('');
  const [email,   setEmail]   = useState('');
  const [phone,   setPhone]   = useState('');
  const [message, setMessage] = useState('');
  const [toEmail, setToEmail] = useState('');
  const [sent,    setSent]    = useState(false);
  const [sending, setSending] = useState(false);
  const [error,   setError]   = useState('');

  // Live-fetched from CT.gov
  const [fetchingContact, setFetchingContact] = useState(false);
  const [researcherEmail, setResearcherEmail] = useState(
    trial?.contact?.email || trial?.researcherEmail || ''
  );
  const [researcherName, setResearcherName] = useState(
    trial?.contact?.name || trial?.researcherName || 'Research Team'
  );

  const trialId = trial?.nctId || trial?.id || '';

  // ── Fetch contact details from ClinicalTrials.gov v2 on modal open ──
  useEffect(() => {
    // Only fetch for NCT IDs — CT.gov API only covers NCT trials
    const nctId = trialId.trim();
    if (!nctId || !/^NCT\d+$/i.test(nctId)) {
      // For CTRI or unknown IDs, just use whatever the backend gave us
      setToEmail(trial?.contact?.email || trial?.researcherEmail || '');
      return;
    }

    // Check localStorage cache first (keyed by NCT ID)
    const cacheKey = `ct_contact_${nctId}`;
    try {
      const cached = localStorage.getItem(cacheKey);
      if (cached) {
        const { email: ce, name: cn } = JSON.parse(cached);
        setResearcherEmail(ce); setResearcherName(cn); setToEmail(ce);
        return;
      }
    } catch { /* ignore */ }

    setFetchingContact(true);
    fetch(
      `https://clinicaltrials.gov/api/v2/studies/${nctId}` +
      `?fields=CentralContactEMail,CentralContactName,LocationContactEMail,LocationContactName`
    )
      .then(r => r.json())
      .then(json => {
        const lo  = json?.protocolSection?.contactsLocationsModule;
        // Central contact is the primary point of contact for the whole trial
        const central  = lo?.centralContacts?.[0];
        // Fall back to first location contact
        const locFirst = lo?.locations?.[0]?.contacts?.[0];

        const foundEmail = central?.email || locFirst?.email || '';
        const foundName  = central?.name  || locFirst?.name  || 'Research Team';

        setResearcherEmail(foundEmail);
        setResearcherName(foundName);
        setToEmail(foundEmail);

        // Cache for 24 hours
        try {
          localStorage.setItem(cacheKey, JSON.stringify({
            email: foundEmail, name: foundName, ts: Date.now()
          }));
        } catch { /* quota */ }
      })
      .catch(() => {
        // Network error — fall back silently to whatever backend gave us
        setToEmail(trial?.contact?.email || '');
      })
      .finally(() => setFetchingContact(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trialId]);

  const handleSubmit = () => {
    if (!name.trim() || !email.trim() || !message.trim()) {
      setError('Please fill in name, email and message.'); return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError('Please enter a valid email address.'); return;
    }
    setError(''); setSending(true);

    const subject = encodeURIComponent(
      `Clinical Trial Inquiry — ${trialId}: ${trial.title}`
    );
    const body = encodeURIComponent(
`Dear ${researcherName},

I am writing to express my interest in the following clinical trial:

Trial Title : ${trial.title}
Trial ID    : ${trialId}

---------------------------------
Patient Details
---------------------------------
Name    : ${name}
Email   : ${email}${phone ? `\nPhone   : ${phone}` : ''}

---------------------------------
Message
---------------------------------
${message}

I would appreciate information about eligibility criteria and the enrollment process.

Regards,
${name}
${email}`
    );

    // Use a temporary hidden <a> and programmatic click — this is the only
    // reliable cross-browser way to open mailto: without navigating away.
    const to         = toEmail.trim() || '';
    const mailtoLink = `mailto:${to}?subject=${subject}&body=${body}`;

    const a = document.createElement('a');
    a.href  = mailtoLink;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    // Small delay so the browser registers the click before we remove the element
    setTimeout(() => { document.body.removeChild(a); }, 200);

    setSending(false);
    setSent(true);
  };

  const overlayStyle = {
    position: 'fixed', inset: 0, zIndex: 1000,
    background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(6px)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem',
  };
  const modalStyle = {
    background: 'rgba(14,2,36,0.98)', border: '1px solid rgba(133,105,228,0.3)',
    borderRadius: '16px', padding: '1.5rem', maxWidth: '520px', width: '100%',
    maxHeight: '90vh', overflowY: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.7)',
    color: '#fff',
  };
  const inputStyle = {
    width: '100%', background: 'rgba(133,105,228,0.07)',
    border: '1px solid rgba(133,105,228,0.2)', borderRadius: '8px',
    padding: '8px 10px', color: '#fff', fontSize: '12px',
    outline: 'none', fontFamily: 'inherit',
  };
  const labelStyle = {
    fontSize: '11px', color: 'rgba(166,140,238,0.7)',
    display: 'block', marginBottom: '4px',
  };

  return (
    <div style={overlayStyle} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={modalStyle}>

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
          <div style={{ flex: 1, paddingRight: '12px' }}>
            <div style={{ fontSize: '10px', fontFamily: 'monospace', color: '#A68CEE', textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: '4px' }}>
              Contact Researcher
            </div>
            <h3 style={{ fontSize: '13px', fontWeight: 700, color: '#fff', lineHeight: 1.4, marginBottom: '4px' }}>
              {trial.title}
            </h3>
            <div style={{ fontSize: '11px', color: 'rgba(166,140,238,0.6)', fontFamily: 'monospace' }}>
              {trialId}
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'rgba(133,105,228,0.1)', border: '1px solid rgba(133,105,228,0.2)', borderRadius: '8px', width: '32px', height: '32px', color: '#A68CEE', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <svg viewBox="0 0 16 16" fill="none" width="14"><path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>
          </button>
        </div>

        {/* Researcher info strip */}
        <div style={{ background: 'rgba(133,105,228,0.06)', border: '1px solid rgba(133,105,228,0.15)', borderRadius: '10px', padding: '10px 14px', marginBottom: '1rem', display: 'flex', gap: '10px', alignItems: 'center' }}>
          <div style={{ width: '34px', height: '34px', borderRadius: '9px', background: 'linear-gradient(135deg,#510993,#8569E4)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: '13px', flexShrink: 0 }}>
            {researcherName.charAt(0).toUpperCase()}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: '12.5px', color: '#fff', display: 'flex', alignItems: 'center', gap: '6px' }}>
              {researcherName}
              {fetchingContact && (
                <span style={{ width: 10, height: 10, border: '1.5px solid rgba(166,140,238,0.3)', borderTopColor: '#A68CEE', borderRadius: '50%', display: 'inline-block', animation: 'spin 0.7s linear infinite' }}/>
              )}
            </div>
            <div style={{ fontSize: '11px', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              color: fetchingContact ? 'rgba(166,140,238,0.4)' : researcherEmail ? '#A68CEE' : 'rgba(249,115,22,0.7)' }}>
              {fetchingContact
                ? 'Looking up contact on ClinicalTrials.gov…'
                : researcherEmail || '⚠ Email not found — enter manually below'}
            </div>
          </div>
          <svg viewBox="0 0 20 20" fill="none" width="16" style={{ color: researcherEmail ? '#A68CEE' : 'rgba(166,140,238,0.25)', flexShrink: 0 }}>
            <rect x="2" y="4" width="16" height="12" rx="2" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M2 7l8 5 8-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        </div>

        {/* Trial pills */}
        <div style={{ display: 'flex', gap: '6px', marginBottom: '1.1rem', flexWrap: 'wrap' }}>
          {trial.status && <span style={{ fontSize: '10.5px', background: 'rgba(133,105,228,0.12)', color: '#C7AFF7', borderRadius: '5px', padding: '3px 9px', border: '1px solid rgba(133,105,228,0.2)' }}>{trial.status}</span>}
          {trial.score  && <span style={{ fontSize: '10.5px', background: 'rgba(133,105,228,0.12)', color: '#A68CEE', borderRadius: '5px', padding: '3px 9px', border: '1px solid rgba(133,105,228,0.2)' }}>Match: {trial.score}%</span>}
          {trial.band   && <span style={{ fontSize: '10.5px', background: 'rgba(133,105,228,0.12)', color: '#a78bfa', borderRadius: '5px', padding: '3px 9px', border: '1px solid rgba(133,105,228,0.2)' }}>{trial.band}</span>}
        </div>

        {sent ? (
          /* ── Success state ── */
          <div style={{ textAlign: 'center', padding: '1.5rem 0' }}>
            <svg viewBox="0 0 48 48" fill="none" width="52" style={{ margin: '0 auto 1rem', display: 'block' }}>
              <circle cx="24" cy="24" r="22" stroke="#a78bfa" strokeWidth="1.5"/>
              <path d="M14 24l7 7 13-14" stroke="#a78bfa" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <h4 style={{ fontSize: '15px', fontWeight: 700, marginBottom: '6px' }}>Mail client opened!</h4>
            <p style={{ fontSize: '12px', color: 'rgba(166,140,238,0.7)', marginBottom: '4px' }}>
              Your email app should open with the message pre-filled.
            </p>
            {researcherEmail && (
              <p style={{ fontSize: '11px', color: 'rgba(166,140,238,0.5)', marginBottom: '1.2rem', fontFamily: 'monospace' }}>
                To: {researcherEmail}
              </p>
            )}
            <p style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginBottom: '1.4rem' }}>
              If nothing opened, copy the researcher's email above and send manually.
            </p>
            <button onClick={onClose} style={{ background: 'linear-gradient(130deg,#510993,#8569E4)', border: 'none', borderRadius: '8px', padding: '9px 24px', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: '13px' }}>
              Done
            </button>
          </div>
        ) : (
          /* ── Form ── */
          <div style={{ display: 'flex', flexDirection: 'column', gap: '11px' }}>

            {/* To: Researcher email — auto-fetched from CT.gov, editable as fallback */}
            <div>
              <label style={labelStyle}>
                To (Researcher Email) <span style={{ color: '#e879f9' }}>*</span>
                {fetchingContact && <span style={{ color: '#A68CEE', fontSize: '10px', marginLeft: '6px' }}>⏳ fetching from ClinicalTrials.gov…</span>}
                {!fetchingContact && !researcherEmail && <span style={{ color: '#f97316', fontSize: '10px', marginLeft: '6px' }}>⚠ not found — please enter manually</span>}
                {!fetchingContact && researcherEmail && <span style={{ color: '#10b981', fontSize: '10px', marginLeft: '6px' }}>✓ found on ClinicalTrials.gov</span>}
              </label>
              <input type="email" placeholder="researcher@hospital.org" value={toEmail}
                onChange={e => setToEmail(e.target.value)}
                disabled={fetchingContact}
                style={{ ...inputStyle, borderColor: toEmail ? 'rgba(16,185,129,0.4)' : 'rgba(249,115,22,0.4)', opacity: fetchingContact ? 0.5 : 1 }}/>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <div>
                <label style={labelStyle}>Your Name <span style={{ color: '#e879f9' }}>*</span></label>
                <input type="text" placeholder="Full name" value={name}
                  onChange={e => setName(e.target.value)} style={inputStyle}/>
              </div>
              <div>
                <label style={labelStyle}>Your Email <span style={{ color: '#e879f9' }}>*</span></label>
                <input type="email" placeholder="you@email.com" value={email}
                  onChange={e => setEmail(e.target.value)} style={inputStyle}/>
              </div>
            </div>

            <div>
              <label style={labelStyle}>Phone <span style={{ opacity: .45 }}>(optional)</span></label>
              <input type="tel" placeholder="+91 98765 43210" value={phone}
                onChange={e => setPhone(e.target.value)} style={inputStyle}/>
            </div>

            <div>
              <label style={labelStyle}>Message <span style={{ color: '#e879f9' }}>*</span></label>
              <textarea rows={4}
                placeholder="Briefly describe your condition, current medications, and your interest in this trial…"
                value={message} onChange={e => setMessage(e.target.value)}
                style={{ ...inputStyle, resize: 'vertical' }}/>
            </div>

            {error && (
              <div style={{ background: 'rgba(232,121,249,0.08)', border: '1px solid rgba(232,121,249,0.25)', borderRadius: '7px', padding: '8px 12px', fontSize: '12px', color: '#e879f9' }}>
                {error}
              </div>
            )}

            {/* What will happen note */}
            <div style={{ background: 'rgba(133,105,228,0.05)', border: '1px solid rgba(133,105,228,0.15)', borderRadius: '8px', padding: '9px 12px', fontSize: '11px', color: 'rgba(166,140,238,0.6)', lineHeight: 1.5 }}>
              📧 Clicking <strong style={{ color: '#C7AFF7' }}>Send Message</strong> will open your default mail app with the <strong style={{ color: '#C7AFF7' }}>To</strong>, <strong style={{ color: '#C7AFF7' }}>Subject</strong> and <strong style={{ color: '#C7AFF7' }}>body</strong> already filled in. Just hit Send in your mail app.
            </div>

            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '2px' }}>
              <button onClick={onClose}
                style={{ background: 'transparent', border: '1px solid rgba(133,105,228,0.22)', borderRadius: '8px', padding: '8px 18px', color: 'rgba(166,140,238,0.7)', fontWeight: 600, cursor: 'pointer', fontSize: '12px' }}>
                Cancel
              </button>
              <button onClick={handleSubmit} disabled={sending}
                style={{ background: sending ? 'rgba(133,105,228,0.4)' : 'linear-gradient(130deg,#510993,#8569E4)', border: 'none', borderRadius: '8px', padding: '8px 20px', color: '#fff', fontWeight: 600, cursor: sending ? 'not-allowed' : 'pointer', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                {sending
                  ? <><span style={{ width: 12, height: 12, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', display: 'inline-block', animation: 'spin 0.7s linear infinite' }}/> Opening…</>
                  : '📧 Send Message →'
                }
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════
   ECG CANVAS BACKGROUND
══════════════════════════════════════════ */
const ECGBackground = () => {
  const canvasRef = useRef(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let raf, offset = 0;
    const resize = () => { canvas.width = canvas.offsetWidth; canvas.height = canvas.offsetHeight; };
    resize();
    window.addEventListener('resize', resize);
    const beatShape = (startX, baseY, scale = 1) => [
      [startX, baseY], [startX + 20, baseY], [startX + 28, baseY - 6 * scale],
      [startX + 36, baseY], [startX + 44, baseY], [startX + 52, baseY - 3 * scale],
      [startX + 60, baseY + 36 * scale], [startX + 68, baseY - 24 * scale],
      [startX + 76, baseY + 9 * scale], [startX + 84, baseY], [startX + 100, baseY],
    ];
    const drawLine = (pts, color, alpha, width = 1.5) => {
      ctx.beginPath(); ctx.strokeStyle = color; ctx.globalAlpha = alpha;
      ctx.lineWidth = width; ctx.shadowBlur = 10; ctx.shadowColor = color;
      pts.forEach(([x, y], i) => i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y));
      ctx.stroke(); ctx.shadowBlur = 0;
    };
    const animate = () => {
      raf = requestAnimationFrame(animate);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.globalAlpha = 1;
      const lines = [
        { y: canvas.height * 0.22, color: '#8569E4', alpha: 0.24, scale: 1.2 },
        { y: canvas.height * 0.52, color: '#A68CEE', alpha: 0.15, scale: 0.85 },
        { y: canvas.height * 0.78, color: '#C7AFF7', alpha: 0.10, scale: 0.6 },
      ];
      lines.forEach(({ y, color, alpha, scale }) => {
        const period = 420;
        for (let r = -1; r < Math.ceil(canvas.width / period) + 2; r++) {
          const x = r * period - (offset % period);
          ctx.beginPath(); ctx.strokeStyle = color; ctx.globalAlpha = alpha * 0.45;
          ctx.lineWidth = 1.2; ctx.shadowBlur = 0;
          ctx.moveTo(x - period, y); ctx.lineTo(x, y); ctx.stroke();
          drawLine(beatShape(x, y, scale), color, alpha, 1.6);
          ctx.beginPath(); ctx.strokeStyle = color; ctx.globalAlpha = alpha * 0.45;
          ctx.lineWidth = 1.2; ctx.moveTo(x + 100, y); ctx.lineTo(x + period, y); ctx.stroke();
        }
      });
      ctx.globalAlpha = 1;
      offset += 1.5;
    };
    animate();
    return () => { window.removeEventListener('resize', resize); cancelAnimationFrame(raf); };
  }, []);
  return <canvas ref={canvasRef} className="ecg-canvas" />;
};

/* ══════════════════════════════════════════
   FLOATING PARTICLES
══════════════════════════════════════════ */
const HealthParticles = () => {
  const dots = Array.from({ length: 20 }, (_, i) => ({
    id: i, x: Math.random() * 100, y: Math.random() * 100,
    size: 3 + Math.random() * 9, dur: 7 + Math.random() * 11,
    delay: Math.random() * 9, type: i % 3,
  }));
  return (
    <div className="health-particles">
      {dots.map(d => (
        <div key={d.id} className={`hp hp-t${d.type}`}
          style={{ left:`${d.x}%`, top:`${d.y}%`, width:d.size, height:d.size,
            animationDuration:`${d.dur}s`, animationDelay:`${d.delay}s` }} />
      ))}
    </div>
  );
};

/* ══════════════════════════════════════════
   COUNT UP HOOK
══════════════════════════════════════════ */
const useCountUp = (target, duration = 1000) => {
  const [value, setValue] = useState(0);
  useEffect(() => {
    let start = 0;
    const step = Math.ceil(target / (duration / 16));
    const t = setInterval(() => {
      start = Math.min(start + step, target);
      setValue(start);
      if (start >= target) clearInterval(t);
    }, 16);
    return () => clearInterval(t);
  }, [target, duration]);
  return value;
};

/* ══════════════════════════════════════════
   STATS ROW
══════════════════════════════════════════ */
const StatsRow = () => {
  const { trialData } = useTrialData();
  const stats = trialData?.statsData ?? {
    totalTrials: 0, matchedTrials: 0, eligibilityScore: 0, nearbyTrials: 0,
  };

  const t = useCountUp(stats.totalTrials,      1200);
  const m = useCountUp(stats.matchedTrials,    900);
  const e = useCountUp(stats.eligibilityScore, 1100);
  const n = useCountUp(stats.nearbyTrials,     700);

  const cards = [
    { label: 'Total Trials Evaluated', value: t, suffix: '', color: 'blue', delay: 0,
      icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg> },
    { label: 'Eligible Trials', value: m, suffix: '', color: 'teal', delay: 80,
      icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg> },
    { label: 'Top Eligibility Score', value: e, suffix: '%', color: 'green', delay: 160,
      icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> },
    { label: 'Excellent Matches (80+)', value: n, suffix: '', color: 'violet', delay: 240,
      icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg> },
  ];

  return (
    <div className="stats-row">
      {cards.map(c => (
        <div key={c.label} className={`stat-card sc-${c.color}`} style={{ animationDelay: `${c.delay}ms` }}>
          <div className={`stat-icon si-${c.color}`}>{c.icon}</div>
          <div className="stat-info">
            <span className="stat-value">{c.value}{c.suffix}</span>
            <span className="stat-label">{c.label}</span>
          </div>
          <div className="stat-bar-track"><div className={`stat-bar-fill sbf-${c.color}`} /></div>
        </div>
      ))}
    </div>
  );
};

/* ══════════════════════════════════════════
   PATIENT PROFILE
══════════════════════════════════════════ */
const PatientProfile = () => {
  const { trialData } = useTrialData();
  const patient = trialData?.patientData ?? {
    name: 'No report uploaded', age: '—', gender: '—', condition: '—',
    bmi: '—', noHeartDisease: '—', hba1c: '—', egfr: '—',
    creatinine: '—', fastingGlucose: '—',
  };
  const [open, setOpen] = useState(false);

  return (
    <div className="card patient-profile">
      <div className="card-header-row">
        <div className="patient-avatar-wrap">
          <svg viewBox="0 0 40 40" fill="none" width="38">
            <circle cx="20" cy="20" r="18" fill="rgba(14,165,233,0.12)" stroke="#0ea5e9" strokeWidth="1.2"/>
            <circle cx="20" cy="15" r="6" fill="#0ea5e9"/>
            <path d="M8 34c0-6.627 5.373-12 12-12s12 5.373 12 12" fill="#0ea5e9" opacity="0.7"/>
          </svg>
          <div>
            <h2 className="card-title">Patient Profile</h2>
            <div className="patient-name">{patient.name}</div>
          </div>
        </div>
        <button className="expand-btn" onClick={() => setOpen(o => !o)}>
          <svg viewBox="0 0 16 16" fill="none" width="14"
            style={{ transform: open ? 'rotate(180deg)' : 'none', transition: '.22s' }}>
            <path d="M3 6l5 5 5-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
          </svg>
        </button>
      </div>

      <div className="profile-details">
        {[
          { l: 'Age',       v: `${patient.age}${patient.gender ? ` · ${patient.gender}` : ''}` },
          { l: 'Condition', v: patient.condition, cls: 'val-blue' },
          { l: 'BMI',       v: patient.bmi },
          { l: 'Fasting Glucose', v: patient.fastingGlucose, cls: 'val-green' },
        ].map(r => (
          <div key={r.l} className="profile-row">
            <span className="profile-label">{r.l}</span>
            <span className={`profile-value ${r.cls || ''}`}>{r.v}</span>
          </div>
        ))}
        {open && <>
          <div className="profile-row anim-in">
            <span className="profile-label">HbA1c</span>
            <span className="profile-value val-amber">{patient.hba1c}</span>
          </div>
          <div className="profile-row anim-in">
            <span className="profile-label">eGFR</span>
            <span className="profile-value">{patient.egfr}</span>
          </div>
          <div className="profile-row anim-in">
            <span className="profile-label">Creatinine</span>
            <span className="profile-value">{patient.creatinine}</span>
          </div>
        </>}
      </div>

      <div className="vitals-strip">
        {[{ e: '🧪', v: patient.fastingGlucose }, { e: '🩺', v: patient.egfr }, { e: '💉', v: patient.hba1c }].map(v => (
          <div key={v.v} className="vital-pill"><span>{v.e}</span><span>{v.v}</span></div>
        ))}
      </div>
    </div>
  );
};

/* ══════════════════════════════════════════
   TRIAL MATCHES — with working buttons
══════════════════════════════════════════ */
const TrialMatches = ({ onContactTrial }) => {
  const { trialData } = useTrialData();
  const [filter,   setFilter]   = useState('All');
  const [expanded, setExpanded] = useState(null);

  const trialList = trialData?.trialsData ?? [];
  const phases = ['All', 'Eligible', 'Likely Eligible', 'Not Eligible'];

  const visible = filter === 'All'
    ? trialList
    : trialList.filter(t => t.status === filter);

  if (!trialData) {
    return (
      <div className="card trial-matches">
        <h2 className="card-title">Top Clinical Trial Matches</h2>
        <p style={{ opacity: .5, padding: '1rem' }}>Upload a report to see matches.</p>
      </div>
    );
  }

  return (
    <div className="card trial-matches">
      <div className="card-header-row">
        <h2 className="card-title">Top Clinical Trial Matches</h2>
        <div className="phase-filters">
          {phases.map(p => (
            <button key={p} className={`phase-btn ${filter === p ? 'phase-btn-on' : ''}`}
              onClick={() => setFilter(p)}>{p}</button>
          ))}
        </div>
      </div>

      <div className="trial-cards-new">
        {visible.map((trial, i) => (
          <div key={trial.id}
            className={`trial-card-new tc-${trial.theme} ${expanded === trial.id ? 'tc-open' : ''}`}
            style={{ animationDelay: `${i * 60}ms` }}>

            <div className="tc-header" onClick={() => setExpanded(expanded === trial.id ? null : trial.id)}>
              <div className="tc-left">
                <span className={`tc-dot dot-${trial.theme}`} />
                <div>
                  <div className="tc-title" title={trial.title}>
                    {trial.title.length > 72 ? trial.title.slice(0, 72) + '…' : trial.title}
                  </div>
                  <div className="tc-meta">
                    {trial.band} · Rank #{trial.id} · Confidence {trial.confidence}%
                  </div>
                </div>
              </div>
              <div className="tc-right">
                <span className={`tc-badge badge-${trial.theme}`}>{trial.score}%</span>
                <svg viewBox="0 0 14 14" fill="none" width="12"
                  style={{ transform: expanded === trial.id ? 'rotate(180deg)' : 'none', transition: '.2s', opacity: .4 }}>
                  <path d="M3 5l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              </div>
            </div>

            <div className="tc-bar-track">
              <div className={`tc-bar-fill tbf-${trial.theme}`} style={{ width: `${trial.score}%` }} />
            </div>

            {expanded === trial.id && (
              <div className="tc-detail anim-in">
                {trial.whyMatched?.length > 0 && (
                  <div style={{ marginBottom: '0.5rem' }}>
                    <span className="td-lbl" style={{ display: 'block', marginBottom: '0.25rem' }}>✅ Why Matched</span>
                    {trial.whyMatched.map((f, fi) => (
                      <span key={fi} style={{ display: 'inline-block', fontSize: '0.72rem', background: 'rgba(16,185,129,0.12)',
                        color: '#10b981', borderRadius: '4px', padding: '2px 7px', marginRight: '4px', marginBottom: '4px' }}>{f}</span>
                    ))}
                  </div>
                )}

                {trial.explanationCards?.length > 0 && (
                  <div style={{ marginBottom: '0.75rem' }}>
                    <span className="td-lbl" style={{ display: 'block', marginBottom: '0.4rem' }}>📊 SHAP Factors</span>
                    {trial.explanationCards.map((card, ci) => (
                      <div key={ci} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem',
                        marginBottom: '0.3rem', fontSize: '0.74rem' }}>
                        <span style={{ color: card.color, fontWeight: 700, minWidth: 16 }}>{card.direction_icon}</span>
                        <span style={{ flex: 1, opacity: 0.85 }}>{card.label}</span>
                        <span style={{ color: card.color, fontWeight: 600 }}>{card.impact_pct > 0 ? '+' : ''}{card.impact_pct.toFixed(1)}%</span>
                        <div style={{ width: 60, height: 4, background: 'rgba(255,255,255,0.08)', borderRadius: 2, overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: `${Math.min(Math.abs(card.impact_pct) * 5, 100)}%`,
                            background: card.color, borderRadius: 2 }} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="tc-detail-grid">
                  <div><span className="td-lbl">NCT ID</span><span className="td-val" style={{ fontSize: '0.72rem' }}>{trial.nctId}</span></div>
                  <div><span className="td-lbl">Priority</span><span className={`td-val ${trial.priority === 'High' ? 'st-green' : ''}`}>{trial.priority}</span></div>
                  <div><span className="td-lbl">Status</span><span className={`td-val ${trial.statusCls}`}>{trial.status}</span></div>
                  <div><span className="td-lbl">Confidence</span><span className="td-val">{trial.confidence}%</span></div>
                </div>

                <p style={{ fontSize: '0.75rem', opacity: 0.6, margin: '0.5rem 0 0.75rem' }}>{trial.action}</p>

                <div className="tc-actions">
                  {/* View Details → smart URL based on trial ID format */}
                  <button className="btn btn-primary"
                    onClick={() => window.open(trialDetailsUrl(trial.nctId), '_blank')}>
                    View Details →
                  </button>
                  {/* Contact Researcher → opens ContactModal */}
                  <button className="btn btn-outline"
                    onClick={() => onContactTrial && onContactTrial(trial)}>
                    Contact Researcher
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

/* ══════════════════════════════════════════
   MATCHED TRIALS MAP — Google Maps showing
   exactly the trials from TrialDataContext
══════════════════════════════════════════ */
const MatchedTrialsMap = ({ onContactTrial }) => {
  const { trialData } = useTrialData();
  const [selectedTrial, setSelectedTrial] = useState(null);
  const mapRef = useRef(null);

  const { isLoaded, loadError } = useJsApiLoader({
    id: 'google-map-script',
    googleMapsApiKey: GMAPS_API_KEY,
    libraries: LIBRARIES,
  });

  // Convert matched trials from context into map-ready pins.
  // We use a deterministic geocode lookup cache to avoid re-fetching on re-render.
  const [geocodedTrials, setGeocodedTrials] = useState([]);
  const geocodeCache = useRef({});

  const rawTrials = trialData?.trialsData ?? [];

  useEffect(() => {
    if (!isLoaded || rawTrials.length === 0) return;
    let cancelled = false;

    const geocodeCity = async (city) => {
      const cacheKey = `geo_${city}`;

      // 1. In-memory cache
      if (geocodeCache.current[cacheKey]) return geocodeCache.current[cacheKey];

      // 2. sessionStorage cache
      const cached = cacheGet(cacheKey);
      if (cached) { geocodeCache.current[cacheKey] = cached; return cached; }

      // 3. Google Maps Geocoder
      return new Promise((resolve) => {
        const geocoder = new window.google.maps.Geocoder();
        geocoder.geocode({ address: `${city}, India` }, (results, status) => {
          if (status === 'OK' && results[0]) {
            const loc = {
              lat: results[0].geometry.location.lat(),
              lng: results[0].geometry.location.lng(),
            };
            geocodeCache.current[cacheKey] = loc;
            cacheSet(cacheKey, loc);
            resolve(loc);
          } else {
            // Fallback: India center with a small deterministic offset so pins don't stack
            const fallback = { lat: 22.9734 + (Math.random() - 0.5) * 4, lng: 78.6569 + (Math.random() - 0.5) * 4 };
            resolve(fallback);
          }
        });
      });
    };

    const run = async () => {
      // Try to pull the full geocoded list from session cache
      const sessionKey = `matched_geo_${rawTrials.map(t => t.nctId || t.id).join('_')}`;
      const sessionHit = cacheGet(sessionKey);
      if (sessionHit && !cancelled) { setGeocodedTrials(sessionHit); return; }

      const results = await Promise.all(
        rawTrials.map(async (trial) => {
          // Extract a city hint from the trial title or use a default
          const cityHint = trial.city || trial.location || 'New Delhi';
          const loc = await geocodeCity(cityHint);
          return { ...trial, lat: loc.lat, lng: loc.lng };
        })
      );
      if (!cancelled) {
        setGeocodedTrials(results);
        cacheSet(sessionKey, results);
      }
    };

    run();
    return () => { cancelled = true; };
  }, [isLoaded, rawTrials.length]);

  const onMapLoad = useCallback(map => { mapRef.current = map; }, []);

  const focusTrial = (trial) => {
    setSelectedTrial(trial);
    mapRef.current?.panTo({ lat: trial.lat, lng: trial.lng });
    mapRef.current?.setZoom(13);
  };

  // Colour by eligibility score band
  const trialColor = (trial) => {
    if (trial.score >= 80) return '#10b981';
    if (trial.score >= 60) return '#A68CEE';
    if (trial.score >= 40) return '#f97316';
    return '#c084fc';
  };

  if (!trialData) {
    return (
      <div className="card trial-map-card">
        <h2 className="card-title-dark map-title">Trial Location Map</h2>
        <div style={{ height: 210, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: .4, fontSize: '13px' }}>
          Upload a report to see trial locations.
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="card trial-map-card">
        <h2 className="card-title-dark map-title">Trial Location Map</h2>
        <div style={{ padding: '1rem', color: '#e879f9', fontSize: '12px' }}>
          Google Maps failed to load. Check <code>VITE_GOOGLE_MAPS_API_KEY</code> in your <code>.env</code>.
        </div>
      </div>
    );
  }

  return (
    <div className="card trial-map-card">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
        <h2 className="card-title-dark map-title" style={{ marginBottom: 0 }}>Trial Location Map</h2>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {[
            { label: '80+', color: '#10b981' },
            { label: '60–79', color: '#A68CEE' },
            { label: '40–59', color: '#f97316' },
            { label: '<40', color: '#c084fc' },
          ].map(l => (
            <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '10px', color: 'rgba(166,140,238,0.7)', fontFamily: 'monospace' }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: l.color, display: 'inline-block' }}/>
              {l.label}%
            </div>
          ))}
        </div>
      </div>

      <div className="map-container" style={{ height: 300 }}>
        {!isLoaded ? (
          <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', color: 'rgba(166,140,238,0.6)', fontSize: '13px' }}>
            <span style={{ width: 18, height: 18, border: '2px solid rgba(133,105,228,0.3)', borderTopColor: '#A68CEE', borderRadius: '50%', display: 'inline-block', animation: 'spin 0.8s linear infinite' }}/>
            Loading map…
          </div>
        ) : (
          <GoogleMap
            mapContainerStyle={{ width: '100%', height: '100%', borderRadius: '10px' }}
            center={INDIA_CENTER}
            zoom={5}
            options={{
              styles: MAP_STYLES,
              zoomControl: true,
              mapTypeControl: false,
              streetViewControl: false,
              fullscreenControl: true,
              clickableIcons: false,
            }}
            onLoad={onMapLoad}
          >
            {geocodedTrials.map(trial => (
              <Marker
                key={trial.nctId || trial.id}
                position={{ lat: trial.lat, lng: trial.lng }}
                icon={markerIcon(trialColor(trial), 30)}
                title={trial.title}
                zIndex={selectedTrial?.id === trial.id ? 100 : 50}
                onClick={() => focusTrial(trial)}
              />
            ))}

            {selectedTrial && (
              <InfoWindow
                position={{ lat: selectedTrial.lat, lng: selectedTrial.lng }}
                onCloseClick={() => setSelectedTrial(null)}
                options={{ pixelOffset: { width: 0, height: -36 } }}
              >
                <div style={{
                  background: '#0e0224', color: '#fff', borderRadius: '10px',
                  padding: '12px', maxWidth: '260px', fontFamily: 'Outfit, sans-serif',
                }}>
                  <div style={{ display: 'flex', gap: '6px', marginBottom: '6px', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: '10px', background: trialColor(selectedTrial) + '22', color: trialColor(selectedTrial), borderRadius: '4px', padding: '2px 7px', border: `1px solid ${trialColor(selectedTrial)}44` }}>
                      {selectedTrial.score}% match
                    </span>
                    <span style={{ fontSize: '10px', background: 'rgba(133,105,228,0.12)', color: '#A68CEE', borderRadius: '4px', padding: '2px 7px' }}>
                      {selectedTrial.band}
                    </span>
                  </div>
                  <div style={{ fontWeight: 700, fontSize: '12px', marginBottom: '4px', lineHeight: 1.3 }}>
                    {selectedTrial.title.length > 80 ? selectedTrial.title.slice(0, 80) + '…' : selectedTrial.title}
                  </div>
                  <div style={{ fontSize: '10.5px', color: 'rgba(166,140,238,0.7)', fontFamily: 'monospace', marginBottom: '8px' }}>
                    {selectedTrial.nctId}
                  </div>
                  <div style={{ fontSize: '11px', color: 'rgba(199,175,247,0.6)', marginBottom: '10px' }}>
                    Confidence: {selectedTrial.confidence}% · Priority: {selectedTrial.priority}
                  </div>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    <button
                      onClick={() => window.open(trialDetailsUrl(selectedTrial.nctId), '_blank')}
                      style={{ flex: 1, background: 'linear-gradient(130deg,#510993,#8569E4)', border: 'none', borderRadius: '7px', padding: '7px 10px', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: '11px' }}>
                      View Details →
                    </button>
                    <button
                      onClick={() => { setSelectedTrial(null); onContactTrial && onContactTrial(selectedTrial); }}
                      style={{ flex: 1, background: 'transparent', border: '1px solid rgba(133,105,228,0.3)', borderRadius: '7px', padding: '7px 10px', color: '#A68CEE', fontWeight: 600, cursor: 'pointer', fontSize: '11px' }}>
                      Contact
                    </button>
                  </div>
                </div>
              </InfoWindow>
            )}
          </GoogleMap>
        )}
      </div>

    </div>
  );
};

/* ══════════════════════════════════════════
   ELIGIBILITY PANEL
══════════════════════════════════════════ */
const EligibilityPanel = () => {
  const { trialData } = useTrialData();
  const initReqs = trialData?.eligibilityData?.requirements ?? [];
  const suggestions = trialData?.eligibilityData?.suggestions ?? ['Upload a report to see suggestions.'];

  const [checked, setChecked] = useState([]);
  useEffect(() => {
    setChecked(initReqs.map(r => r.met));
  }, [initReqs.length]);

  const liveScore = checked.length
    ? Math.round((checked.filter(Boolean).length / checked.length) * 100)
    : 0;

  return (
    <div className="card eligibility-panel">
      <h2 className="card-title-dark panel-title">Eligibility Breakdown</h2>

      {initReqs.length === 0 ? (
        <p style={{ opacity: .5, padding: '0.75rem 0' }}>Upload a report to see eligibility details.</p>
      ) : (
        <>
          <div className="requirements-list">
            {initReqs.map((req, i) => (
              <div key={req.id}
                className={`requirement-item ${req.warn ? 'item-warning' : ''} ${!checked[i] ? 'item-unmet' : ''}`}>
                <button className={`req-checkbox ${checked[i] ? 'req-checked' : ''}`}
                  onClick={() => setChecked(c => { const n = [...c]; n[i] = !n[i]; return n; })}>
                  {checked[i] && <svg viewBox="0 0 12 12" fill="none" width="10">
                    <path d="M2 6l3 3 5-5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>}
                </button>
                <span className="req-label">
                  {req.warn && <svg className="warning-icon" width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2L1 21h22L12 2zm0 3.99L19.53 19H4.47L12 5.99zM11 16h2v2h-2zm0-6h2v5h-2z"/>
                  </svg>}
                  {req.label}
                  {req.note && <span className="req-note"> {req.note}</span>}
                </span>
                <span className={`req-status ${checked[i] ? 'text-success' : 'text-muted'}`}>
                  {checked[i]
                    ? <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                    : <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>}
                  {checked[i] ? 'Met' : 'Not Met'}
                </span>
              </div>
            ))}
          </div>

          <div className="readiness-section">
            <div className="readiness-header">
              <span className="readiness-label">Readiness Score:</span>
              <span className="readiness-value text-success">{liveScore}%</span>
            </div>
            <div className="readiness-bar-bg">
              <div className="readiness-bar-fill bg-success"
                style={{ width: `${liveScore}%`, transition: 'width .5s cubic-bezier(.4,0,.2,1)' }} />
            </div>
          </div>

          <div className="suggestions-section">
            <h3 className="suggestions-title">💡 Improve Eligibility:</h3>
            <ul className="suggestions-list">
              {suggestions.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        </>
      )}
    </div>
  );
};

/* ══════════════════════════════════════════
   ANALYTICS OVERVIEW
══════════════════════════════════════════ */
const AnalyticsOverview = () => {
  const { trialData } = useTrialData();
  const [hov, setHov] = useState(null);

  const chartData = trialData?.analyticsData ?? [
    { id: 'none', label: 'No data yet', color: '#374151', value: 1 },
  ];
  const total = chartData.reduce((a, b) => a + b.value, 0);

  let off = 0;
  const segs = chartData.map(d => {
    const pct = (d.value / total) * 100;
    const seg = { ...d, pct, off };
    off += pct;
    return seg;
  });

  const recentActivity = trialData
    ? [
        { icon: '🔬', text: `Top trial scored ${trialData.statsData.eligibilityScore}%`,   time: 'just now' },
        { icon: '📊', text: `${trialData.statsData.matchedTrials} eligible trials found`,   time: 'just now' },
        { icon: '✅', text: `${trialData.statsData.nearbyTrials} excellent matches (80+)`,  time: 'just now' },
      ]
    : [
        { icon: '⏳', text: 'Waiting for report upload…', time: '' },
      ];

  return (
    <div className="card analytics-overview">
      <h2 className="card-title-dark analytics-title">Analytics Overview</h2>
      <h3 className="chart-subtitle">Score Distribution</h3>

      <div className="chart-container">
        <div className="donut-chart">
          <svg viewBox="0 0 42 42" className="circular-chart">
            <circle cx="21" cy="21" r="15.9155" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="6" />
            {segs.map(seg => (
              <circle key={seg.id} cx="21" cy="21" r="15.9155" fill="none"
                stroke={seg.color}
                strokeWidth={hov === seg.id ? 7.5 : 6}
                strokeOpacity={hov === null || hov === seg.id ? 1 : 0.4}
                strokeDasharray={`${seg.pct} ${100 - seg.pct}`}
                strokeDashoffset={-(seg.off - 25)}
                style={{ transition: 'stroke-width .2s, stroke-opacity .2s', cursor: 'pointer' }}
                onMouseEnter={() => setHov(seg.id)}
                onMouseLeave={() => setHov(null)}
              />
            ))}
            <text x="21" y="19.5" textAnchor="middle" fontSize="5.5" fill="currentColor" fontWeight="800" className="donut-center-num">
              {hov ? segs.find(s => s.id === hov)?.value : total}
            </text>
            <text x="21" y="24" textAnchor="middle" fontSize="2.8" fill="currentColor" opacity="0.5">
              {hov ? segs.find(s => s.id === hov)?.label : 'trials'}
            </text>
          </svg>
        </div>

        <div className="chart-legend">
          {segs.map(seg => (
            <div key={seg.id} className={`legend-item ${hov === seg.id ? 'legend-item-hov' : ''}`}
              onMouseEnter={() => setHov(seg.id)} onMouseLeave={() => setHov(null)}>
              <span className="legend-color" style={{ backgroundColor: seg.color }} />
              <span className="legend-label">{seg.label}</span>
              <span className="legend-count">{seg.value}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="activity-feed">
        <div className="af-title">Recent Activity</div>
        {recentActivity.map((a, i) => (
          <div key={i} className="af-row">
            <span className="af-icon">{a.icon}</span>
            <span className="af-text">{a.text}</span>
            <span className="af-time">{a.time}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

/* ══════════════════════════════════════════
   MAIN DASHBOARD
══════════════════════════════════════════ */
export default function Dashboard() {
  const [theme, setTheme] = useState('dark-theme');
  const { trialData, setTrialData } = useTrialData();

  // Global contact modal state — shared between TrialMatches and MatchedTrialsMap
  const [contactTrial, setContactTrial] = useState(null);

  useEffect(() => { document.documentElement.className = theme; }, [theme]);

  // trialData persistence is handled entirely inside TrialDataContext —
  // it rehydrates from localStorage on mount and saves on every fetch.

  return (
    <div className={`app-container ${theme}`}>
      <ECGBackground />
      <HealthParticles />

      {/* Contact modal — rendered at root level so both sections can trigger it */}
      {contactTrial && (
        <ContactModal trial={contactTrial} onClose={() => setContactTrial(null)} />
      )}

      <header className="dash-header">
        <div className="dash-logo">
          <span className="logo-cross">✚</span>
          <span>Nex<b>Trial</b></span>
        </div>
        <div className="dash-header-right">
          <div className="dash-search">
            <svg viewBox="0 0 16 16" fill="none" width="13">
              <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M11 11l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            <input placeholder="Search trials…" />
          </div>
          <button className="notif-btn">
            <svg viewBox="0 0 20 20" fill="none" width="16">
              <path d="M10 2a6 6 0 0 1 6 6v3.5l1.5 2H2.5L4 11.5V8a6 6 0 0 1 6-6z" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M8 16a2 2 0 0 0 4 0" stroke="currentColor" strokeWidth="1.5"/>
            </svg>
            <span className="notif-badge">{trialData?.statsData?.matchedTrials ?? 0}</span>
          </button>
          <button className="theme-btn" onClick={() => setTheme(t => t === 'dark-theme' ? 'light-theme' : 'dark-theme')}>
            {theme === 'dark-theme' ? '☀️' : '🌙'}
          </button>
          <div className="dash-avatar">
            {trialData?.patientData?.name?.charAt(0) ?? '?'}
          </div>
        </div>
      </header>

      {!trialData && (
        <div style={{
          margin: '1rem 2rem', padding: '0.75rem 1.25rem',
          background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.2)',
          borderRadius: '10px', color: 'rgba(255,255,255,0.6)', fontSize: '0.85rem',
          display: 'flex', alignItems: 'center', gap: '0.6rem',
        }}>
          <span>📄</span>
          <span>No report uploaded yet. Go to <strong>Report Upload</strong> to analyse a PDF and populate this dashboard.</span>
        </div>
      )}

      <div className="main-layout">
        <main className="content-area">
          <StatsRow />
          <div className="dashboard-grid">
            <div className="left-column">
              <PatientProfile />
              <TrialMatches onContactTrial={setContactTrial} />
              <MatchedTrialsMap onContactTrial={setContactTrial} />
            </div>
            <div className="right-column">
              <EligibilityPanel />
              <AnalyticsOverview />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}