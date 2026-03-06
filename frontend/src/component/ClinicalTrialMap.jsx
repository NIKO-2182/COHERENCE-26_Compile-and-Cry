// ClinicalTrialMap.jsx — Uses geoPoint lat/lon directly from ClinicalTrials.gov API v2
// No geocoding, no hardcoded coords — every pin is exact hospital-level location
// Google Maps needs VITE_GOOGLE_MAPS_API_KEY in .env

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { GoogleMap, useJsApiLoader, Marker, InfoWindow, Circle } from "@react-google-maps/api";
import "./ClinicalTrialMap.css";

/* ─── Config ──────────────────────────────────────────── */
const GMAPS_API_KEY    = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
const NEARBY_RADIUS_KM = 50;
const INDIA_CENTER     = { lat: 22.9734, lng: 78.6569 };
const INDIA_ZOOM       = 5;
const LIBRARIES        = ["places"];

/* ─── ClinicalTrials.gov v2 ───────────────────────────── */
const CT_API_BASE = "https://clinicaltrials.gov/api/v2/studies";
const CT_FIELDS = [
  "NCTId", "BriefTitle", "OverallStatus", "Phase", "Condition",
  "StartDate", "LeadSponsorName", "BriefSummary",
  "LocationFacility", "LocationCity", "LocationState", "LocationCountry",
  "LocationGeoPoint",   // ← exact lat/lon per location, direct from API
  "LocationContactName", "LocationContactPhone", "LocationContactEMail",
  "CentralContactName", "CentralContactPhone", "CentralContactEMail",
].join(",");

/* ─── Phase colours ───────────────────────────────────── */
const PHASE_COLOR = {
  "Phase I":       "#f59e0b",
  "Phase I/II":    "#f97316",
  "Phase II":      "#0ea5e9",
  "Phase III":     "#10b981",
  "Phase IV":      "#6366f1",
  "Observational": "#8b5cf6",
};

const ALL_PHASES = ["All Phases", "Phase I", "Phase I/II", "Phase II", "Phase III", "Phase IV", "Observational"];

/* ─── Google Maps dark style ──────────────────────────── */
const MAP_STYLES = [
  { elementType: "geometry",                stylers: [{ color: "#04090f" }] },
  { elementType: "labels.text.fill",        stylers: [{ color: "#4e6e88" }] },
  { elementType: "labels.text.stroke",      stylers: [{ color: "#020c18" }] },
  { featureType: "administrative",          elementType: "geometry",         stylers: [{ color: "#0c1523" }] },
  { featureType: "administrative.country",  elementType: "labels.text.fill", stylers: [{ color: "#5a8aaa" }] },
  { featureType: "administrative.locality", elementType: "labels.text.fill", stylers: [{ color: "#5a8aaa" }] },
  { featureType: "poi",                     elementType: "labels.text.fill", stylers: [{ color: "#4e6e88" }] },
  { featureType: "poi.park",                elementType: "geometry",         stylers: [{ color: "#080f1c" }] },
  { featureType: "road",                    elementType: "geometry",         stylers: [{ color: "#0c1523" }] },
  { featureType: "road",                    elementType: "geometry.stroke",  stylers: [{ color: "#060d1a" }] },
  { featureType: "road",                    elementType: "labels.text.fill", stylers: [{ color: "#3a5a72" }] },
  { featureType: "road.highway",            elementType: "geometry",         stylers: [{ color: "#0e1f36" }] },
  { featureType: "road.highway",            elementType: "labels.text.fill", stylers: [{ color: "#4a7a99" }] },
  { featureType: "transit",                 elementType: "geometry",         stylers: [{ color: "#080f1c" }] },
  { featureType: "water",                   elementType: "geometry",         stylers: [{ color: "#020c18" }] },
  { featureType: "water",                   elementType: "labels.text.fill", stylers: [{ color: "#1a3a55" }] },
];

/* ─── Marker icons ────────────────────────────────────── */
function markerIcon(color = "#0ea5e9", size = 34) {
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

function patientIcon() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="42" height="42" viewBox="0 0 42 42">
    <circle cx="21" cy="21" r="19" fill="#0ea5e9" fill-opacity="0.12" stroke="#0ea5e9" stroke-width="1.4"/>
    <circle cx="21" cy="21" r="10" fill="#0ea5e9"/>
    <circle cx="21" cy="21" r="5" fill="white"/>
  </svg>`;
  return {
    url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
    scaledSize: { width: 42, height: 42 },
    anchor: { x: 21, y: 21 },
  };
}

/* ─── Parse raw API study ─────────────────────────────── */
function parseStudy(study) {
  const p  = study.protocolSection || {};
  const id = p.identificationModule;
  const st = p.statusModule;
  const de = p.descriptionModule;
  const sp = p.sponsorCollaboratorsModule;
  const co = p.conditionsModule;
  const lo = p.contactsLocationsModule;
  const ds = p.designModule;

  const rawPhase = (ds?.phases?.[0] || "").replace("PHASE", "Phase ").trim();
  const phase = !rawPhase || rawPhase === "Phase  NA" ? "Observational"
    : rawPhase
        .replace("Phase 12", "Phase I/II")
        .replace("Phase I2",  "Phase I/II")
        .replace("Phase 1",  "Phase I")
        .replace("Phase 2",  "Phase II")
        .replace("Phase 3",  "Phase III")
        .replace("Phase 4",  "Phase IV");

  const locations = (lo?.locations || []).filter(l =>
    (l.country || "").toLowerCase().includes("india")
  );
  if (!locations.length) return null;

  // Prefer a location that has geoPoint coordinates
  const primary = locations.find(l => l.geoPoint?.lat && l.geoPoint?.lon) || locations[0];

  // ── Read lat/lon directly from the API response — no geocoding needed ──
  const lat = primary.geoPoint?.lat ?? null;
  const lon = primary.geoPoint?.lon ?? null;

  // Drop trials with no coordinates at all
  if (lat === null || lon === null) return null;

  const city  = primary.city  || "Unknown";
  const state = primary.state || "Unknown";

  const centralContact = (lo?.centralContacts || [])[0] || {};
  const contact = {
    name:  primary.contacts?.[0]?.name  || centralContact.name  || "Study Team",
    email: primary.contacts?.[0]?.email || centralContact.email || "",
    phone: primary.contacts?.[0]?.phone || centralContact.phone || "",
  };

  return {
    id:          id?.nctId || "",
    title:       id?.briefTitle || "Untitled Study",
    institution: primary.facility || "Unknown Institution",
    city, state,
    lat,
    lng: lon,
    phase, contact,
    status:      st?.overallStatus === "RECRUITING" ? "Recruiting" : (st?.overallStatus || ""),
    condition:   co?.conditions?.[0] || "Unknown",
    startDate:   st?.startDateStruct?.date || "",
    sponsor:     sp?.leadSponsor?.name || "Unknown",
    description: (de?.briefSummary || "").slice(0, 200) + "…",
    allLocations: locations.map(l => ({
      city: l.city || "", state: l.state || "",
      facility: l.facility || "",
      lat: l.geoPoint?.lat, lng: l.geoPoint?.lon,
    })),
  };
}

/* ─── Contact Modal ───────────────────────────────────── */
function ContactModal({ trial, onClose }) {
  const [name,    setName]    = useState("");
  const [email,   setEmail]   = useState("");
  const [phone,   setPhone]   = useState("");
  const [message, setMessage] = useState("");
  const [sent,    setSent]    = useState(false);
  const [sending, setSending] = useState(false);
  const [error,   setError]   = useState("");

  const handleSubmit = async () => {
    if (!name.trim() || !email.trim() || !message.trim()) {
      setError("Please fill in name, email and message."); return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError("Please enter a valid email address."); return;
    }
    setError(""); setSending(true);
    const subject = encodeURIComponent(`Clinical Trial Inquiry — ${trial.id}: ${trial.title}`);
    const body = encodeURIComponent(
`Dear ${trial.contact.name},

I am writing to express interest in your clinical trial:
Trial: ${trial.title}
Trial ID: ${trial.id}
Institution: ${trial.institution}

Patient Name: ${name}
Patient Email: ${email}
${phone ? `Patient Phone: ${phone}\n` : ""}
Message:
${message}

I would appreciate information about eligibility and enrollment.

Regards,
${name}`
    );
    await new Promise(r => setTimeout(r, 800));
    window.location.href = `mailto:${trial.contact.email}?subject=${subject}&body=${body}`;
    setSending(false); setSent(true);
  };

  return (
    <div className="ctmap-modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="ctmap-modal">
        <div className="ctmap-modal-header">
          <div>
            <div className="ctmap-modal-eyebrow">Contact Researcher</div>
            <h3 className="ctmap-modal-title">{trial.title}</h3>
            <div className="ctmap-modal-inst">{trial.institution} · {trial.city}</div>
          </div>
          <button className="ctmap-modal-close" onClick={onClose} aria-label="Close">
            <svg viewBox="0 0 16 16" fill="none" width="14">
              <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
            </svg>
          </button>
        </div>
        {sent ? (
          <div className="ctmap-modal-success">
            <svg viewBox="0 0 48 48" fill="none" width="48">
              <circle cx="24" cy="24" r="22" stroke="#10b981" strokeWidth="1.5"/>
              <path d="M14 24l7 7 13-14" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <h4>Message sent!</h4>
            <p>Your mail client opened pre-filled for <strong>{trial.contact.name}</strong>.</p>
            <p className="ctmap-modal-success-note">
              Or email: <a href={`mailto:${trial.contact.email}`}>{trial.contact.email}</a>
            </p>
            <button className="ctmap-modal-btn" onClick={onClose}>Done</button>
          </div>
        ) : (
          <>
            <div className="ctmap-modal-researcher">
              <div className="ctmap-modal-r-avatar">{trial.contact.name.charAt(0)}</div>
              <div>
                <div className="ctmap-modal-r-name">{trial.contact.name}</div>
                <div className="ctmap-modal-r-email">{trial.contact.email || "Contact via NCT ID"}</div>
                {trial.contact.phone && <div className="ctmap-modal-r-phone">{trial.contact.phone}</div>}
              </div>
            </div>
            <div className="ctmap-modal-pills">
              <span className="ctmap-modal-pill" style={{ color: PHASE_COLOR[trial.phase], background: PHASE_COLOR[trial.phase] + "18" }}>{trial.phase}</span>
              <span className="ctmap-modal-pill ctmap-pill-green">{trial.status}</span>
              <span className="ctmap-modal-pill">{trial.condition}</span>
              <span className="ctmap-modal-pill">{trial.id}</span>
            </div>
            <div className="ctmap-modal-form">
              <div className="ctmap-modal-row">
                <div className="ctmap-modal-field">
                  <label>Your Name <span>*</span></label>
                  <input type="text" placeholder="Full name" value={name} onChange={e => setName(e.target.value)}/>
                </div>
                <div className="ctmap-modal-field">
                  <label>Email <span>*</span></label>
                  <input type="email" placeholder="you@email.com" value={email} onChange={e => setEmail(e.target.value)}/>
                </div>
              </div>
              <div className="ctmap-modal-field">
                <label>Phone <span className="optional">(optional)</span></label>
                <input type="tel" placeholder="+91 98765 43210" value={phone} onChange={e => setPhone(e.target.value)}/>
              </div>
              <div className="ctmap-modal-field">
                <label>Message <span>*</span></label>
                <textarea rows={4} placeholder="Briefly describe your condition and interest in this trial…"
                  value={message} onChange={e => setMessage(e.target.value)}/>
              </div>
              {error && <div className="ctmap-modal-error">{error}</div>}
              <div className="ctmap-modal-actions">
                <button className="ctmap-modal-btn-secondary" onClick={onClose}>Cancel</button>
                <button className="ctmap-modal-btn" onClick={handleSubmit} disabled={sending}>
                  {sending ? <><span className="ctmap-spin ctmap-spin-sm"/>Sending…</> : "Send Message →"}
                </button>
              </div>
              <p className="ctmap-modal-note">
                This will open your mail client pre-filled. Your info is shared only with {trial.institution}.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/* ─── View Toggle ─────────────────────────────────────── */
function ViewToggle({ view, onChange }) {
  return (
    <div className="ctmap-view-toggle">
      <button className={view === "nearby" ? "active" : ""} onClick={() => onChange("nearby")}>
        <svg viewBox="0 0 16 16" fill="none" width="13"><circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.6"/><path d="M8 2v1M8 13v1M2 8h1M13 8h1" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
        Near Me
      </button>
      <button className={view === "india" ? "active" : ""} onClick={() => onChange("india")}>
        <svg viewBox="0 0 16 16" fill="none" width="13"><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.6"/><path d="M2 8h12M8 2c-2 2-2 8 0 12M8 2c2 2 2 8 0 12" stroke="currentColor" strokeWidth="1.2"/></svg>
        All India
      </button>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   MAIN COMPONENT
═══════════════════════════════════════════════════════ */
export default function ClinicalTrialMap({ patientConditions = [] }) {
  const [trials,      setTrials]      = useState([]);
  const [fetchPhase,  setFetchPhase]  = useState("idle");
  const [fetchError,  setFetchError]  = useState("");

  const [view,            setView]            = useState("nearby");
  const [userLocation,    setUserLocation]    = useState(null);
  const [locating,        setLocating]        = useState(false);
  const [locationError,   setLocationError]   = useState(null);
  const [selectedTrial,   setSelectedTrial]   = useState(null);
  const [contactTrial,    setContactTrial]    = useState(null);
  const [filterState,     setFilterState]     = useState("All India");
  const [filterCity,      setFilterCity]      = useState("All Cities");
  const [filterPhase,     setFilterPhase]     = useState("All Phases");
  const [filterCondition, setFilterCondition] = useState("");
  const [listSearch,      setListSearch]      = useState("");
  const [currentPage,     setCurrentPage]     = useState(1);
  const PAGE_SIZE = 10;
  const mapRef    = useRef(null);
  const listTopRef = useRef(null);

  const { isLoaded, loadError } = useJsApiLoader({
    googleMapsApiKey: GMAPS_API_KEY,
    libraries: LIBRARIES,
  });

  /* ══════════════════════════════════════════════════
     FETCH — lat/lon read directly from geoPoint field.
     Trials appear on map page-by-page as they load.
     Zero geocoding. Zero hardcoded coordinates.
  ══════════════════════════════════════════════════ */
  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      setFetchPhase("fetching");
      setTrials([]);

      try {
        let pageToken = null;
        let page      = 0;
        const MAX_PAGES = 10;

        do {
          const params = new URLSearchParams({
            "query.locn":           "India",
            "filter.overallStatus": "RECRUITING",
            "pageSize":             "100",
            "format":               "json",
            "fields":               CT_FIELDS,
          });
          if (pageToken) params.set("pageToken", pageToken);

          const res = await fetch(`${CT_API_BASE}?${params}`);
          if (!res.ok) throw new Error(`API error ${res.status}`);
          const json = await res.json();

          // Parse and append each page immediately — progressive rendering
          const pageParsed = (json.studies || []).map(parseStudy).filter(Boolean);
          if (cancelled) return;
          setTrials(prev => [...prev, ...pageParsed]);

          pageToken = json.nextPageToken || null;
          page++;
          if (cancelled) return;
        } while (pageToken && page < MAX_PAGES);

        if (!cancelled) setFetchPhase("done");
      } catch (err) {
        if (!cancelled) { setFetchError(err.message); setFetchPhase("error"); }
      }
    };

    run();
    return () => { cancelled = true; };
  }, []);

  /* ── Geolocation ── */
  const requestLocation = useCallback(() => {
    if (!navigator.geolocation) { setLocationError("Geolocation not supported."); return; }
    setLocating(true); setLocationError(null);
    navigator.geolocation.getCurrentPosition(
      pos => { setUserLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude }); setLocating(false); },
      ()  => { setLocating(false); setLocationError("Location access denied. Showing All India view."); setView("india"); },
      { timeout: 8000, maximumAge: 60000 }
    );
  }, []);

  useEffect(() => { requestLocation(); }, [requestLocation]);

  /* ── State/city filter lists — built from live data, not hardcoded ── */
  const stateList = useMemo(() => {
    const states = [...new Set(trials.map(t => t.state).filter(s => s && s !== "Unknown"))].sort();
    return ["All India", ...states];
  }, [trials]);

  const cityList = useMemo(() => {
    let source = filterState !== "All India" ? trials.filter(t => t.state === filterState) : trials;
    const cities = [...new Set(source.map(t => t.city).filter(c => c && c !== "Unknown"))].sort();
    return ["All Cities", ...cities];
  }, [trials, filterState]);

  /* ── Filtered trials ── */
  const filteredTrials = useMemo(() => {
    let list = trials;

    if (view === "nearby" && userLocation) {
      list = list.filter(t => {
        const R    = 6371;
        const dLat = (t.lat - userLocation.lat) * Math.PI / 180;
        const dLng = (t.lng - userLocation.lng) * Math.PI / 180;
        const a = Math.sin(dLat / 2) ** 2 +
          Math.cos(userLocation.lat * Math.PI / 180) *
          Math.cos(t.lat          * Math.PI / 180) *
          Math.sin(dLng / 2) ** 2;
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)) <= NEARBY_RADIUS_KM;
      });
      if (list.length === 0) list = trials;
    }

    if (filterState !== "All India")  list = list.filter(t => t.state === filterState);
    if (filterCity  !== "All Cities") list = list.filter(t => t.city  === filterCity);
    if (filterPhase !== "All Phases") list = list.filter(t => t.phase === filterPhase);
    if (filterCondition.trim()) {
      const q = filterCondition.toLowerCase();
      list = list.filter(t => t.condition.toLowerCase().includes(q) || t.title.toLowerCase().includes(q));
    }
    if (listSearch.trim()) {
      const q = listSearch.toLowerCase();
      list = list.filter(t =>
        t.title.toLowerCase().includes(q)       ||
        t.institution.toLowerCase().includes(q) ||
        t.city.toLowerCase().includes(q)        ||
        t.condition.toLowerCase().includes(q)
      );
    }
    return list;
  }, [trials, view, userLocation, filterState, filterCity, filterPhase, filterCondition, listSearch]);

  const mapCenter = useMemo(() => {
    if (view === "nearby" && userLocation) return userLocation;
    if (filterCity !== "All Cities" && filteredTrials.length) return { lat: filteredTrials[0].lat, lng: filteredTrials[0].lng };
    return INDIA_CENTER;
  }, [view, userLocation, filterCity, filteredTrials]);

  const mapZoom = useMemo(() => {
    if (filterCity  !== "All Cities") return 12;
    if (filterState !== "All India")  return 7;
    if (view === "nearby" && userLocation) return 10;
    return INDIA_ZOOM;
  }, [view, userLocation, filterState, filterCity]);

  const onMapLoad    = useCallback(map => { mapRef.current = map; }, []);
  const focusTrial   = t => { setSelectedTrial(t); mapRef.current?.panTo({ lat: t.lat, lng: t.lng }); mapRef.current?.setZoom(15); };
  const resetFilters = () => { setFilterState("All India"); setFilterCity("All Cities"); setFilterPhase("All Phases"); setFilterCondition(""); setListSearch(""); setCurrentPage(1); };

  // Reset to page 1 whenever filters/search change
  const handleFilterState = v  => { setFilterState(v);     setFilterCity("All Cities"); setCurrentPage(1); };
  const handleFilterCity  = v  => { setFilterCity(v);      setCurrentPage(1); };
  const handleFilterPhase = v  => { setFilterPhase(v);     setCurrentPage(1); };
  const handleFilterCond  = v  => { setFilterCondition(v); setCurrentPage(1); };
  const handleListSearch  = v  => { setListSearch(v);      setCurrentPage(1); };
  const activeFilterCount = [
    filterState !== "All India", filterCity !== "All Cities",
    filterPhase !== "All Phases", !!filterCondition.trim(),
  ].filter(Boolean).length;

  const renderBanner = () => {
    if (fetchPhase === "fetching") return (
      <div className="ctmap-fetch-banner ctmap-fetch-banner--info">
        <span className="ctmap-spin"/>
        Fetching live trials from ClinicalTrials.gov…
        {trials.length > 0 && <span className="ctmap-fetch-count">{trials.length} loaded</span>}
      </div>
    );
    if (fetchPhase === "done") return (
      <div className="ctmap-fetch-banner ctmap-fetch-banner--success">
        ✓ <strong>{trials.length}</strong> live recruiting trials · Exact hospital-level coordinates
        <span className="ctmap-fetch-live-dot"/>Live
      </div>
    );
    if (fetchPhase === "error") return (
      <div className="ctmap-fetch-banner ctmap-fetch-banner--error">
        ⚠ {fetchError} — Check your connection or refresh.
      </div>
    );
    return null;
  };

  if (loadError) return (
    <div className="ctmap-error">
      Google Maps failed to load. Check <code>VITE_GOOGLE_MAPS_API_KEY</code> in your <code>.env</code>.
    </div>
  );

  return (
    <>
      {contactTrial && <ContactModal trial={contactTrial} onClose={() => setContactTrial(null)} />}

      <div className="ctmap-wrap">

        {/* Header */}
        <div className="ctmap-section-header">
          <div className="ctmap-section-left">
            <div className="ctmap-title-row">
              <span className="ctmap-pip"/>
              <h2 className="ctmap-title">Clinical Trials in India</h2>
            </div>
            <p className="ctmap-subtitle">
              {trials.length > 0
                ? `${filteredTrials.length} trial${filteredTrials.length !== 1 ? "s" : ""} found${filterState !== "All India" ? ` · ${filterState}` : ""}${filterCity !== "All Cities" ? ` · ${filterCity}` : ""}`
                : "Fetching live data from ClinicalTrials.gov…"
              }
            </p>
          </div>
          <div className="ctmap-section-right">
            <ViewToggle view={view} onChange={v => { setView(v); resetFilters(); }}/>
            {locating && <div className="ctmap-locating"><span className="ctmap-spin"/>Locating…</div>}
            {!locating && view === "nearby" && (
              <button className="ctmap-relocate" onClick={requestLocation}>
                <svg viewBox="0 0 20 20" fill="none" width="13"><circle cx="10" cy="10" r="3" stroke="currentColor" strokeWidth="1.8"/><path d="M10 2v2M10 16v2M2 10h2M16 10h2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>
                Re-detect
              </button>
            )}
          </div>
        </div>

        {renderBanner()}
        {locationError && <div className="ctmap-alert">{locationError}</div>}

        {/* Filters */}
        <div className="ctmap-filters">
          <div className="ctmap-filter-group">
            <label>State</label>
            <select value={filterState} onChange={e => handleFilterState(e.target.value)}>
              {stateList.map(s => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div className="ctmap-filter-group">
            <label>City</label>
            <select value={filterCity} onChange={e => handleFilterCity(e.target.value)}>
              {cityList.map(c => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div className="ctmap-filter-group">
            <label>Phase</label>
            <select value={filterPhase} onChange={e => handleFilterPhase(e.target.value)}>
              {ALL_PHASES.map(p => <option key={p}>{p}</option>)}
            </select>
          </div>
          <div className="ctmap-filter-group ctmap-filter-grow">
            <label>Condition / Keyword</label>
            <div className="ctmap-search-wrap">
              <svg viewBox="0 0 16 16" fill="none" width="13" className="ctmap-search-icon">
                <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M10.5 10.5l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
              <input type="text" placeholder="e.g. Diabetes, Cancer, CKD…"
                value={filterCondition} onChange={e => handleFilterCond(e.target.value)}/>
              {filterCondition && <button className="ctmap-search-clear" onClick={() => handleFilterCond("")}>×</button>}
            </div>
          </div>
          {activeFilterCount > 0 && (
            <button className="ctmap-reset" onClick={resetFilters}>
              Clear {activeFilterCount} filter{activeFilterCount > 1 ? "s" : ""}
            </button>
          )}
        </div>

        {/* Map */}
        <div className="ctmap-map-container">
          {!isLoaded ? (
            <div className="ctmap-skeleton">
              <span className="ctmap-spin ctmap-spin--lg"/>
              <span>Loading Google Maps…</span>
            </div>
          ) : (
            <GoogleMap
              mapContainerStyle={{ width: "100%", height: "100%" }}
              center={mapCenter}
              zoom={mapZoom}
              options={{ styles: MAP_STYLES, zoomControl: true, mapTypeControl: false, streetViewControl: false, fullscreenControl: true, clickableIcons: false }}
              onLoad={onMapLoad}
            >
              {view === "nearby" && userLocation && (
                <>
                  <Marker position={userLocation} icon={patientIcon()} title="Your location" zIndex={200}/>
                  <Circle center={userLocation} radius={NEARBY_RADIUS_KM * 1000}
                    options={{ fillColor: "#0ea5e9", fillOpacity: 0.04, strokeColor: "#0ea5e9", strokeOpacity: 0.18, strokeWeight: 1 }}
                  />
                </>
              )}

              {filteredTrials.map(trial => (
                <Marker
                  key={trial.id}
                  position={{ lat: trial.lat, lng: trial.lng }}
                  icon={markerIcon(PHASE_COLOR[trial.phase] || "#0ea5e9")}
                  title={`${trial.institution} — ${trial.title}`}
                  zIndex={selectedTrial?.id === trial.id ? 100 : 50}
                  onClick={() => setSelectedTrial(trial)}
                />
              ))}

              {selectedTrial && (
                <InfoWindow
                  position={{ lat: selectedTrial.lat, lng: selectedTrial.lng }}
                  onCloseClick={() => setSelectedTrial(null)}
                  options={{ pixelOffset: { width: 0, height: -36 } }}
                >
                  <div className="ctmap-infowin">
                    <div className="ctmap-iw-phase" style={{
                      background:  (PHASE_COLOR[selectedTrial.phase] || "#0ea5e9") + "22",
                      color:        PHASE_COLOR[selectedTrial.phase] || "#0ea5e9",
                      borderColor: (PHASE_COLOR[selectedTrial.phase] || "#0ea5e9") + "44",
                    }}>
                      {selectedTrial.phase}
                    </div>
                    <div className="ctmap-iw-title">{selectedTrial.title}</div>
                    <div className="ctmap-iw-inst">{selectedTrial.institution}</div>
                    <div className="ctmap-iw-desc">{selectedTrial.description}</div>
                    <div className="ctmap-iw-row"><span className="ctmap-iw-label">Condition</span><span>{selectedTrial.condition}</span></div>
                    <div className="ctmap-iw-row"><span className="ctmap-iw-label">Sponsor</span><span>{selectedTrial.sponsor}</span></div>
                    <div className="ctmap-iw-row"><span className="ctmap-iw-label">Status</span><span className="ctmap-iw-status">{selectedTrial.status}</span></div>
                    <div className="ctmap-iw-row">
                      <span className="ctmap-iw-label">Trial ID</span>
                      <a href={`https://clinicaltrials.gov/study/${selectedTrial.id}`} target="_blank" rel="noreferrer"
                        style={{ fontFamily: "monospace", fontSize: "11px", color: "#0ea5e9" }}>
                        {selectedTrial.id} ↗
                      </a>
                    </div>
                    <button className="ctmap-iw-btn" onClick={() => { setSelectedTrial(null); setContactTrial(selectedTrial); }}>
                      Contact Researcher →
                    </button>
                  </div>
                </InfoWindow>
              )}
            </GoogleMap>
          )}
        </div>

        {/* Phase legend */}
        <div className="ctmap-legend">
          {Object.entries(PHASE_COLOR).map(([phase, color]) => (
            <button key={phase}
              className={`ctmap-legend-item ${filterPhase === phase ? "active" : ""}`}
              onClick={() => setFilterPhase(filterPhase === phase ? "All Phases" : phase)}
              style={{ "--leg-color": color }}
            >
              <span className="ctmap-legend-dot"/>
              {phase}
            </button>
          ))}
        </div>

        {/* Trial list */}
        <div className="ctmap-list-header" ref={listTopRef}>
          <span className="ctmap-list-count">
            {filteredTrials.length} trial{filteredTrials.length !== 1 ? "s" : ""}
            {filteredTrials.length > PAGE_SIZE && (
              <span className="ctmap-page-info"> · Page {currentPage} of {Math.ceil(filteredTrials.length / PAGE_SIZE)}</span>
            )}
          </span>
          <div className="ctmap-search-wrap ctmap-list-search">
            <svg viewBox="0 0 16 16" fill="none" width="13" className="ctmap-search-icon">
              <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M10.5 10.5l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            <input type="text" placeholder="Search trials…"
              value={listSearch} onChange={e => handleListSearch(e.target.value)}/>
            {listSearch && <button className="ctmap-search-clear" onClick={() => handleListSearch("")}>×</button>}
          </div>
        </div>

        <div className="ctmap-list">
          {fetchPhase === "fetching" && trials.length === 0 ? (
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="ctmap-card ctmap-card-skeleton" style={{ animationDelay: `${i * 80}ms` }}>
                <div className="ctmap-skel-line ctmap-skel-sm"/>
                <div className="ctmap-skel-line ctmap-skel-lg"/>
                <div className="ctmap-skel-line ctmap-skel-md"/>
              </div>
            ))
          ) : filteredTrials.length === 0 ? (
            <div className="ctmap-empty">
              <svg viewBox="0 0 48 48" fill="none" width="40">
                <circle cx="24" cy="24" r="22" stroke="rgba(14,165,233,.2)" strokeWidth="1.5"/>
                <path d="M24 14v10M24 32v2" stroke="rgba(14,165,233,.5)" strokeWidth="2.5" strokeLinecap="round"/>
              </svg>
              <p>No trials match your current filters.</p>
              <button onClick={resetFilters}>Clear all filters</button>
            </div>
          ) : (
            <>
              {filteredTrials
                .slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
                .map((trial, i) => (
                <div
                  key={trial.id}
                  className={`ctmap-card ${selectedTrial?.id === trial.id ? "ctmap-card--active" : ""}`}
                  onClick={() => focusTrial(trial)}
                  style={{ animationDelay: `${i * 40}ms` }}
                >
                  <div className="ctmap-card-left">
                    <div className="ctmap-card-top-row">
                      <div className="ctmap-card-phase"
                        style={{ background: (PHASE_COLOR[trial.phase] || "#0ea5e9") + "18", color: PHASE_COLOR[trial.phase] || "#0ea5e9" }}>
                        {trial.phase}
                      </div>
                      <span className="ctmap-card-id">{trial.id}</span>
                    </div>
                    <div className="ctmap-card-title">{trial.title}</div>
                    <div className="ctmap-card-inst">{trial.institution}</div>
                    <div className="ctmap-card-meta">
                      <span>{trial.city}, {trial.state}</span>
                      <span className="ctmap-dot">·</span>
                      <span>{trial.condition}</span>
                      <span className="ctmap-dot">·</span>
                      <span className="ctmap-status-badge">{trial.status}</span>
                    </div>
                  </div>
                  <div className="ctmap-card-right">
                    <button className="ctmap-card-contact" onClick={e => { e.stopPropagation(); setContactTrial(trial); }}>
                      Contact
                    </button>
                    <svg viewBox="0 0 14 14" fill="none" width="11" opacity=".3">
                      <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </div>
                </div>
              ))}

              {/* ── Pagination ── */}
              {filteredTrials.length > PAGE_SIZE && (() => {
                const totalPages = Math.ceil(filteredTrials.length / PAGE_SIZE);
                const goTo = p => {
                  setCurrentPage(p);
                  listTopRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                };

                // Build page number array with ellipsis: 1 2 3 … 12 13 14
                const pages = [];
                const delta = 2;
                const left  = currentPage - delta;
                const right = currentPage + delta;
                let last = 0;
                for (let p = 1; p <= totalPages; p++) {
                  if (p === 1 || p === totalPages || (p >= left && p <= right)) {
                    if (last && p - last > 1) pages.push("…");
                    pages.push(p);
                    last = p;
                  }
                }

                return (
                  <div className="ctmap-pagination">
                    {/* Prev */}
                    <button
                      className="ctmap-page-btn ctmap-page-arrow"
                      onClick={() => goTo(currentPage - 1)}
                      disabled={currentPage === 1}
                    >
                      <svg viewBox="0 0 14 14" fill="none" width="12">
                        <path d="M9 11L5 7l4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </button>

                    {pages.map((p, i) =>
                      p === "…" ? (
                        <span key={`ellipsis-${i}`} className="ctmap-page-ellipsis">…</span>
                      ) : (
                        <button
                          key={p}
                          className={`ctmap-page-btn ${currentPage === p ? "ctmap-page-btn--active" : ""}`}
                          onClick={() => goTo(p)}
                        >
                          {p}
                        </button>
                      )
                    )}

                    {/* Next */}
                    <button
                      className="ctmap-page-btn ctmap-page-arrow"
                      onClick={() => goTo(currentPage + 1)}
                      disabled={currentPage === totalPages}
                    >
                      <svg viewBox="0 0 14 14" fill="none" width="12">
                        <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </button>
                  </div>
                );
              })()}
            </>
          )}
        </div>

      </div>
    </>
  );
}