import { useEffect, useRef, useState } from "react";

function useIntersection(options = {}) {
  const ref = useRef(null);
  const [isVisible, setIsVisible] = useState(false);
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setIsVisible(true);
        observer.disconnect();
      }
    }, { threshold: 0.15, ...options });
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return [ref, isVisible];
}

export default function AboutUs() {
  const [scrollY, setScrollY] = useState(0);
  const [heroRef, heroVisible] = useIntersection({ threshold: 0.05 });
  const [missionRef, missionVisible] = useIntersection();
  const [valuesRef, valuesVisible] = useIntersection();
  const [ctaRef, ctaVisible] = useIntersection();

  useEffect(() => {
    const onScroll = () => setScrollY(window.scrollY);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div style={styles.page}>
      {/* NOISE OVERLAY */}
      <div style={styles.noise} />

      {/* ── HERO ── */}
      <section ref={heroRef} style={styles.hero}>
        <div style={{ ...styles.heroBg, transform: `translateY(${scrollY * 0.35}px)` }} />
        <div style={styles.heroOverlay} />

        <div style={styles.heroContent}>
          <p style={{
            ...styles.heroEyebrow,
            opacity: heroVisible ? 1 : 0,
            transform: heroVisible ? "none" : "translateY(20px)",
            transition: "opacity 0.8s ease 0.2s, transform 0.8s ease 0.2s",
          }}>
            Our Story
          </p>

          <h1 style={{
            ...styles.heroTitle,
            opacity: heroVisible ? 1 : 0,
            transform: heroVisible ? "none" : "translateY(40px)",
            transition: "opacity 0.9s ease 0.35s, transform 0.9s ease 0.35s",
          }}>
            ABOUT
            <br />
            <span style={styles.heroTitleOutline}>US</span>
          </h1>

          <p style={{
            ...styles.heroSub,
            opacity: heroVisible ? 1 : 0,
            transform: heroVisible ? "none" : "translateY(30px)",
            transition: "opacity 0.8s ease 0.55s, transform 0.8s ease 0.55s",
          }}>
            Bridging AI and medicine — making clinical trials accessible to every patient who needs them.
          </p>

          <div style={{
            ...styles.heroScrollIndicator,
            opacity: heroVisible ? 1 : 0,
            transition: "opacity 1s ease 1.1s",
          }}>
            <span style={styles.scrollLine} />
            <span style={styles.scrollText}>Scroll</span>
          </div>
        </div>

        <div style={styles.heroBgText}>ABOUT</div>
      </section>

      {/* ── MISSION ── */}
      <section ref={missionRef} style={styles.mission}>
        <div style={styles.missionInner}>
          <div style={{
            ...styles.missionLeft,
            opacity: missionVisible ? 1 : 0,
            transform: missionVisible ? "none" : "translateX(-50px)",
            transition: "opacity 0.9s ease 0.1s, transform 0.9s ease 0.1s",
          }}>
            <span style={styles.missionTag}>Who We Are</span>
            <h2 style={styles.missionHeading}>
              Where AI meets<br /><em style={styles.missionItalic}>medicine</em>
            </h2>
          </div>

          <div style={{
            ...styles.missionRight,
            opacity: missionVisible ? 1 : 0,
            transform: missionVisible ? "none" : "translateX(50px)",
            transition: "opacity 0.9s ease 0.3s, transform 0.9s ease 0.3s",
          }}>
            <p style={styles.missionBody}>
              We are a team of builders competing at a hackathon with one mission: use artificial
              intelligence to connect patients with the clinical trials they deserve. Our system,{" "}
              <strong style={{ color: "#ede8f5" }}>Compile &amp; Cry</strong>, is an AI-powered
              Clinical Trial Matching platform built to make precision medicine a reality — not a privilege.
            </p>
            <p style={styles.missionBody}>
              Starting from raw patient records and thousands of trial criteria, our pipeline ingests,
              parses, matches, and explains — surfacing the right trials for the right people with full
              transparency and zero compromise on patient privacy.
            </p>
            <div style={styles.missionDivider} />
            <p style={styles.missionQuote}>
              "The right trial for the right patient — found in seconds, not months."
            </p>
          </div>
        </div>

        {/* Decorative card
        <div style={{
          ...styles.missionCard,
          opacity: missionVisible ? 1 : 0,
          transform: missionVisible ? "rotate(-2deg)" : "rotate(-2deg) translateY(40px)",
          transition: "opacity 1s ease 0.5s, transform 1s ease 0.5s",
        }}> */}
          {/* <div style={styles.missionCardInner}>
            <div style={styles.missionCardGradient} />
            {/* <span style={styles.missionCardLabel}>Compile &amp; Cry</span> */}
          {/* </div>
        </div> */} 
      </section>

      {/* ── HOW IT WORKS ── */}
      <section ref={valuesRef} style={styles.values}>
        <div style={{
          ...styles.valuesHeader,
          opacity: valuesVisible ? 1 : 0,
          transform: valuesVisible ? "none" : "translateY(30px)",
          transition: "opacity 0.8s ease, transform 0.8s ease",
        }}>
          <span style={styles.sectionTag}>Our Pipeline</span>
          <h2 style={styles.sectionHeading}>How it works</h2>
        </div>

        <div style={styles.valuesList}>
          {[
            {
              num: "01",
              title: "Data Ingestion & Preprocessing",
              desc: "We ingest anonymized patient CSVs and fetch live trial data from ClinicalTrials.gov. Every record is PII-scanned and validated before entering the pipeline.",
            },
            {
              num: "02",
              title: "AI-Powered Criteria Parsing",
              desc: "A fine-tuned BioBERT NER model extracts structured entities — age ranges, lab thresholds, conditions — from raw inclusion/exclusion text, combined with regex post-processing.",
            },
            {
              num: "03",
              title: "Hybrid Matching & Ranking",
              desc: "Rule-based pre-filtering handles hard criteria. XGBoost scores each patient-trial pair using feature vectors: lab diffs, cosine similarity, entity overlap, and geographic distance.",
            },
            {
              num: "04",
              title: "Transparent Explanations",
              desc: "Every match comes with SHAP-driven explanations and human-readable rule reasons — so clinicians and patients understand exactly why a trial was recommended.",
            },
            {
              num: "05",
              title: "Ethics & Privacy Safeguards",
              desc: "All processing is local. No PHI is stored or transmitted. Differential privacy is applied to embeddings. Compliance status is surfaced directly in the dashboard.",
            },
          ].map((v, i) => (
            <div
              key={v.num}
              style={{
                ...styles.valueItem,
                opacity: valuesVisible ? 1 : 0,
                transform: valuesVisible ? "none" : "translateX(-30px)",
                transition: `opacity 0.7s ease ${0.12 * i + 0.1}s, transform 0.7s ease ${0.12 * i + 0.1}s`,
              }}
              className="value-item"
            >
              <span style={styles.valueNum}>{v.num}</span>
              <div style={styles.valueContent}>
                <h3 style={styles.valueTitle}>{v.title}</h3>
                <p style={styles.valueDesc}>{v.desc}</p>
              </div>
              <div style={styles.valueArrow} className="value-arrow">→</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA ── */}
      <section ref={ctaRef} style={styles.cta}>
        <div style={styles.ctaBgAccent} />
        <div style={{
          ...styles.ctaInner,
          opacity: ctaVisible ? 1 : 0,
          transform: ctaVisible ? "none" : "translateY(40px)",
          transition: "opacity 0.9s ease, transform 0.9s ease",
        }}>
          <p style={styles.ctaEyebrow}>Ready to create something?</p>
          <h2 style={styles.ctaHeading}>
            Let's build<br />
            <span style={styles.ctaOutline}>together</span>
          </h2>
          <a href="mailto:hello@studio.com" style={styles.ctaButton} className="cta-btn">
            Get in touch
            <span style={styles.ctaArrow}>↗</span>
          </a>
        </div>
      </section>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=DM+Sans:wght@300;400;500&display=swap');

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #08060f; }

        .value-item:hover { background: rgba(139,92,246,0.06) !important; }
        .value-item:hover .value-arrow { color: #a855f7 !important; transform: translateX(6px) !important; }
        .cta-btn:hover {
          background: #a855f7 !important;
          color: #08060f !important;
          letter-spacing: 0.12em !important;
        }
      `}</style>
    </div>
  );
}

const styles = {
  page: {
    background: "#08060f",
    color: "#ede8f5",
    fontFamily: "'DM Sans', sans-serif",
    overflowX: "hidden",
    position: "relative",
    minHeight: "100vh",
  },
  noise: {
    position: "fixed",
    inset: 0,
    backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='1'/%3E%3C/svg%3E")`,
    opacity: 0.03,
    pointerEvents: "none",
    zIndex: 999,
  },

  /* HERO */
  hero: {
    position: "relative",
    height: "100vh",
    minHeight: 600,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  heroBg: {
    position: "absolute",
    inset: "-20%",
    background: "radial-gradient(ellipse at 60% 40%, #1e0f3f 0%, #08060f 65%)",
    willChange: "transform",
  },
  heroOverlay: {
    position: "absolute",
    inset: 0,
    background: "linear-gradient(to bottom, transparent 40%, #08060f 100%)",
  },
  heroContent: {
    position: "relative",
    zIndex: 2,
    textAlign: "center",
    padding: "0 24px",
  },
  heroEyebrow: {
    display: "inline-block",
    fontFamily: "'DM Sans', sans-serif",
    fontWeight: 300,
    fontSize: "0.8rem",
    letterSpacing: "0.3em",
    textTransform: "uppercase",
    color: "#a855f7",
    marginBottom: 28,
  },
  heroTitle: {
    fontFamily: "'Playfair Display', serif",
    fontWeight: 900,
    fontSize: "clamp(5rem, 15vw, 13rem)",
    lineHeight: 0.9,
    color: "#ede8f5",
    letterSpacing: "-0.02em",
    marginBottom: 32,
  },
  heroTitleOutline: {
    WebkitTextStroke: "2px #a855f7",
    color: "transparent",
  },
  heroSub: {
    fontWeight: 300,
    fontSize: "clamp(0.95rem, 2vw, 1.15rem)",
    color: "rgba(237,232,245,0.6)",
    maxWidth: 480,
    margin: "0 auto 56px",
    lineHeight: 1.7,
  },
  heroScrollIndicator: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 10,
  },
  scrollLine: {
    display: "block",
    width: 1,
    height: 48,
    background: "linear-gradient(to bottom, transparent, #a855f7)",
  },
  scrollText: {
    fontSize: "0.65rem",
    letterSpacing: "0.25em",
    textTransform: "uppercase",
    color: "rgba(237,232,245,0.4)",
  },
  heroBgText: {
    position: "absolute",
    bottom: "-4vw",
    left: "50%",
    transform: "translateX(-50%)",
    fontFamily: "'Playfair Display', serif",
    fontWeight: 900,
    fontSize: "clamp(6rem, 22vw, 20rem)",
    color: "transparent",
    WebkitTextStroke: "1px rgba(139,92,246,0.08)",
    whiteSpace: "nowrap",
    pointerEvents: "none",
    zIndex: 1,
    letterSpacing: "-0.02em",
  },

  /* MISSION */
  mission: {
    padding: "clamp(80px, 10vw, 140px) clamp(24px, 8vw, 120px)",
    position: "relative",
  },
  missionInner: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "clamp(40px, 6vw, 100px)",
    alignItems: "start",
    maxWidth: 1200,
    margin: "0 auto",
  },
  missionLeft: { transition: "all 0.9s ease" },
  missionTag: {
    display: "inline-block",
    fontSize: "0.72rem",
    letterSpacing: "0.3em",
    textTransform: "uppercase",
    color: "#a855f7",
    marginBottom: 20,
    fontWeight: 500,
  },
  missionHeading: {
    fontFamily: "'Playfair Display', serif",
    fontWeight: 700,
    fontSize: "clamp(2.2rem, 5vw, 3.8rem)",
    lineHeight: 1.15,
    color: "#ede8f5",
  },
  missionItalic: {
    fontStyle: "italic",
    color: "#a855f7",
  },
  missionRight: { paddingTop: 8, transition: "all 0.9s ease" },
  missionBody: {
    fontSize: "clamp(0.9rem, 1.5vw, 1rem)",
    lineHeight: 1.85,
    color: "rgba(237,232,245,0.65)",
    marginBottom: 20,
    fontWeight: 300,
  },
  missionDivider: {
    width: 40,
    height: 1,
    background: "rgba(139,92,246,0.45)",
    margin: "28px 0",
  },
  missionQuote: {
    fontFamily: "'Playfair Display', serif",
    fontStyle: "italic",
    fontSize: "clamp(0.95rem, 1.8vw, 1.1rem)",
    color: "rgba(237,232,245,0.5)",
    lineHeight: 1.7,
  },
  missionCard: {
    position: "absolute",
    right: "clamp(24px, 5vw, 80px)",
    top: "clamp(40px, 8vw, 80px)",
    width: "clamp(120px, 14vw, 180px)",
    height: "clamp(160px, 18vw, 240px)",
    borderRadius: 16,
    overflow: "hidden",
    border: "1px solid rgba(139,92,246,0.25)",
  },
  missionCardInner: {
    width: "100%",
    height: "100%",
    background: "linear-gradient(135deg, #120a2e 0%, #1e0f3f 100%)",
    position: "relative",
    display: "flex",
    alignItems: "flex-end",
    padding: 16,
  },
  missionCardGradient: {
    position: "absolute",
    inset: 0,
    background: "radial-gradient(circle at 70% 30%, rgba(139,92,246,0.18), transparent 70%)",
  },
  missionCardLabel: {
    position: "relative",
    fontFamily: "'Playfair Display', serif",
    fontSize: "0.72rem",
    color: "#a855f7",
    letterSpacing: "0.12em",
    lineHeight: 1.5,
  },

  /* HOW IT WORKS */
  values: {
    padding: "clamp(80px, 10vw, 140px) clamp(24px, 8vw, 120px)",
    background: "rgba(0,0,0,0.2)",
  },
  valuesHeader: {
    marginBottom: "clamp(40px, 6vw, 64px)",
  },
  sectionTag: {
    display: "inline-block",
    fontSize: "0.72rem",
    letterSpacing: "0.3em",
    textTransform: "uppercase",
    color: "#a855f7",
    marginBottom: 16,
    fontWeight: 500,
  },
  sectionHeading: {
    fontFamily: "'Playfair Display', serif",
    fontWeight: 700,
    fontSize: "clamp(2rem, 5vw, 3.5rem)",
    color: "#ede8f5",
    lineHeight: 1.2,
  },
  valuesList: {
    maxWidth: 860,
    display: "flex",
    flexDirection: "column",
    gap: 0,
  },
  valueItem: {
    display: "flex",
    alignItems: "center",
    gap: 32,
    padding: "clamp(20px, 3vw, 32px) 24px",
    borderBottom: "1px solid rgba(255,255,255,0.05)",
    transition: "background 0.3s ease",
    borderRadius: 8,
    cursor: "default",
  },
  valueNum: {
    fontFamily: "'Playfair Display', serif",
    fontWeight: 700,
    fontSize: "clamp(1.4rem, 3vw, 2rem)",
    color: "rgba(139,92,246,0.28)",
    minWidth: 52,
    lineHeight: 1,
  },
  valueContent: { flex: 1 },
  valueTitle: {
    fontFamily: "'Playfair Display', serif",
    fontWeight: 700,
    fontSize: "clamp(1rem, 2vw, 1.3rem)",
    color: "#ede8f5",
    marginBottom: 6,
  },
  valueDesc: {
    fontSize: "0.88rem",
    lineHeight: 1.75,
    color: "rgba(237,232,245,0.5)",
    fontWeight: 300,
    maxWidth: 560,
  },
  valueArrow: {
    fontSize: "1.2rem",
    color: "rgba(237,232,245,0.2)",
    transition: "transform 0.3s ease, color 0.3s ease",
  },

  /* CTA */
  cta: {
    padding: "clamp(100px, 14vw, 180px) clamp(24px, 8vw, 120px)",
    position: "relative",
    overflow: "hidden",
    textAlign: "center",
  },
  ctaBgAccent: {
    position: "absolute",
    inset: 0,
    background: "radial-gradient(ellipse at 50% 60%, rgba(139,92,246,0.08) 0%, transparent 70%)",
    pointerEvents: "none",
  },
  ctaInner: { position: "relative", zIndex: 1 },
  ctaEyebrow: {
    fontSize: "0.75rem",
    letterSpacing: "0.3em",
    textTransform: "uppercase",
    color: "#a855f7",
    marginBottom: 24,
    fontWeight: 500,
  },
  ctaHeading: {
    fontFamily: "'Playfair Display', serif",
    fontWeight: 900,
    fontSize: "clamp(3rem, 10vw, 8rem)",
    lineHeight: 1,
    color: "#ede8f5",
    marginBottom: 56,
    letterSpacing: "-0.02em",
  },
  ctaOutline: {
    WebkitTextStroke: "2px rgba(139,92,246,0.65)",
    color: "transparent",
    display: "block",
  },
  ctaButton: {
    display: "inline-flex",
    alignItems: "center",
    gap: 12,
    padding: "18px 44px",
    border: "1px solid rgba(139,92,246,0.55)",
    borderRadius: 100,
    color: "#ede8f5",
    textDecoration: "none",
    fontSize: "0.88rem",
    letterSpacing: "0.12em",
    textTransform: "uppercase",
    fontWeight: 500,
    transition: "background 0.35s ease, color 0.35s ease, letter-spacing 0.35s ease",
  },
  ctaArrow: {
    fontSize: "1rem",
    lineHeight: 1,
  },
};