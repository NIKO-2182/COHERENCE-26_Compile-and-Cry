import { useState, useMemo, useRef, useEffect } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import Navbar from "./common/Navbar";
import { TrialDataProvider } from "./context/TrialDataContext";
import Dashboard from "./component/Dashboard";
import MedicalReportUpload from "./component/ReportUpload";
import ClinicalTrials from "./component/AboutUs";

const PARTICLE_COUNT = 15000;

const generateSphere = () => {
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const u = Math.random(), v = Math.random();
    const theta = u * 2.0 * Math.PI, phi = Math.acos(2.0 * v - 1.0);
    const r = 10 + Math.random() * 2;
    positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = r * Math.cos(phi);
  }
  return positions;
};

const generateSaturn = () => {
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    if (i < PARTICLE_COUNT * 0.4) {
      const u = Math.random(), v = Math.random();
      const theta = u * 2.0 * Math.PI, phi = Math.acos(2.0 * v - 1.0);
      const r = 6;
      positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      positions[i * 3 + 2] = r * Math.cos(phi);
    } else {
      const angle = Math.random() * Math.PI * 2;
      const r = 9 + Math.random() * 7;
      positions[i * 3] = Math.cos(angle) * r;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 1;
      positions[i * 3 + 2] = Math.sin(angle) * r;
    }
  }
  const tilt = 0.4;
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const y = positions[i * 3 + 1], z = positions[i * 3 + 2];
    positions[i * 3 + 1] = y * Math.cos(tilt) - z * Math.sin(tilt);
    positions[i * 3 + 2] = y * Math.sin(tilt) + z * Math.cos(tilt);
  }
  return positions;
};

const generateHelix = () => {
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const t = (i / PARTICLE_COUNT) * Math.PI * 20;
    const offset = i % 2 === 0 ? 0 : Math.PI;
    const radius = 6, height = (i / PARTICLE_COUNT) * 40 - 20;
    const noise = () => (Math.random() - 0.5) * 1.5;
    positions[i * 3] = Math.cos(t + offset) * radius + noise();
    positions[i * 3 + 1] = height + noise();
    positions[i * 3 + 2] = Math.sin(t + offset) * radius + noise();
  }
  return positions;
};

const generatePlus = () => {
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const axis = Math.floor(Math.random() * 3);
    const length = (Math.random() - 0.5) * 25;
    const thickness = 3;
    const n1 = (Math.random() - 0.5) * thickness, n2 = (Math.random() - 0.5) * thickness;
    if (axis === 0) { positions[i*3]=length; positions[i*3+1]=n1; positions[i*3+2]=n2; }
    else if (axis === 1) { positions[i*3]=n1; positions[i*3+1]=length; positions[i*3+2]=n2; }
    else { positions[i*3]=n1; positions[i*3+1]=n2; positions[i*3+2]=length; }
  }
  return positions;
};

const ParticleSystem = () => {
  const pointsRef = useRef();
  const [activeShapeIndex, setActiveShapeIndex] = useState(0);

  const shapeTargets = useMemo(() => [
    generateSphere(), generateSaturn(), generateHelix(), generatePlus()
  ], []);

  const currentPositions = useMemo(() => new Float32Array(shapeTargets[0]), [shapeTargets]);

  const particleColors = useMemo(() => {
    const colors = new Float32Array(PARTICLE_COUNT * 3);
    const tempColor = new THREE.Color();
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const hue = 0.72 + Math.random() * 0.13;
      tempColor.setHSL(hue, 0.9, 0.6);
      colors[i * 3] = tempColor.r;
      colors[i * 3 + 1] = tempColor.g;
      colors[i * 3 + 2] = tempColor.b;
    }
    return colors;
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveShapeIndex(prev => (prev + 1) % shapeTargets.length);
    }, 4000);
    return () => clearInterval(interval);
  }, [shapeTargets.length]);

  useFrame(() => {
    if (!pointsRef.current) return;
    const pos = pointsRef.current.geometry.attributes.position.array;
    const target = shapeTargets[activeShapeIndex];
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const i3 = i * 3;
      pos[i3]   += (target[i3]   - pos[i3])   * 0.05;
      pos[i3+1] += (target[i3+1] - pos[i3+1]) * 0.05;
      pos[i3+2] += (target[i3+2] - pos[i3+2]) * 0.05;
    }
    pointsRef.current.geometry.attributes.position.needsUpdate = true;
    pointsRef.current.rotation.y += 0.005;
    pointsRef.current.rotation.x += 0.002;
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={PARTICLE_COUNT} array={currentPositions} itemSize={3} />
        <bufferAttribute attach="attributes-color" count={PARTICLE_COUNT} array={particleColors} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial size={0.15} vertexColors blending={THREE.AdditiveBlending} transparent opacity={0.8} depthWrite={false} />
    </points>
  );
};

// ── SPLASH SCREEN ──────────────────────────────────────────
const SplashScreen = ({ onDone }) => {
  const [phase, setPhase] = useState("splash"); // splash | shutting | done

  useEffect(() => {
    if (phase !== "splash") return;
    const trigger = () => setPhase("shutting");
    window.addEventListener("wheel", trigger, { once: true });
    window.addEventListener("click", trigger, { once: true });
    window.addEventListener("touchstart", trigger, { once: true });
    return () => {
      window.removeEventListener("wheel", trigger);
      window.removeEventListener("click", trigger);
      window.removeEventListener("touchstart", trigger);
    };
  }, [phase]);

  useEffect(() => {
    if (phase !== "shutting") return;
    const timer = setTimeout(() => {
      setPhase("done");
      onDone(); // ← tell App.js splash is finished
    }, 950);
    return () => clearTimeout(timer);
  }, [phase, onDone]);

  if (phase === "done") return null;

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700&display=swap');

        .splash-wrap {
          position: fixed;
          inset: 0;
          z-index: 9999;
          background: #000;
          display: flex;
          align-items: center;
          justify-content: center;
          transform: translateY(0%);
          transition: transform 0.9s cubic-bezier(0.76, 0, 0.24, 1);
        }
        .splash-wrap.shutting {
          transform: translateY(-100%);
        }
        .splash-canvas-wrap {
          position: absolute;
          inset: 0;
        }
        .splash-text {
          position: relative;
          z-index: 10;
          pointer-events: none;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 0.75rem;
          animation: revealUp 1.2s cubic-bezier(0.22, 1, 0.36, 1) both;
        }
        @keyframes revealUp {
          from { opacity: 0; transform: translateY(24px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .splash-title {
          font-family: 'Bricolage Grotesque', sans-serif;
          font-size: clamp(4rem, 9vw, 9rem);
          font-weight: 700;
          color: #fbf5e2;
          letter-spacing: -0.02em;
          text-shadow:
            0 0 10px rgba(215,199,216,0.8),
            0 0 20px rgba(230,218,229,0.6),
            0 0 40px rgba(219,204,215,0.4),
            0 0 80px rgba(85,2,85,0.6);
        }
        .splash-hint {
          font-family: 'Bricolage Grotesque', sans-serif;
          font-size: clamp(0.75rem, 1.4vw, 1rem);
          color: rgba(200, 180, 210, 0.45);
          letter-spacing: 0.32em;
          text-transform: uppercase;
          animation: revealUp 1.4s 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
        }
        .arrow-cue {
          margin-top: 1.8rem;
          display: flex;
          flex-direction: column;
          align-items: center;
          animation: revealUp 1.4s 0.9s cubic-bezier(0.22, 1, 0.36, 1) both;
        }
        .arrow-line {
          width: 1px;
          height: 36px;
          background: linear-gradient(to bottom, transparent, rgba(200,180,210,0.45));
        }
        .arrow-chevron {
          width: 10px;
          height: 10px;
          border-right: 1px solid rgba(200,180,210,0.5);
          border-bottom: 1px solid rgba(200,180,210,0.5);
          transform: rotate(45deg) translateY(-4px);
          animation: chevronBounce 1.5s ease-in-out infinite;
        }
        @keyframes chevronBounce {
          0%, 100% { opacity: 0.3; transform: rotate(45deg) translateY(-4px); }
          50%       { opacity: 0.9; transform: rotate(45deg) translateY(3px); }
        }
      `}</style>

      <div className={`splash-wrap ${phase === "shutting" ? "shutting" : ""}`}>
        <div className="splash-canvas-wrap">
          <Canvas camera={{ position: [0, 0, 35], fov: 75 }}>
            <ParticleSystem />
          </Canvas>
        </div>
        <div className="splash-text">
          <h1 className="splash-title">NexTrial</h1>
          <p className="splash-hint">Scroll or click to enter</p>
          <div className="arrow-cue">
            <div className="arrow-line" />
            <div className="arrow-chevron" />
          </div>
        </div>
      </div>
    </>
  );
};

// ── MAIN APP ───────────────────────────────────────────────
function App() {
  const [showSplash, setShowSplash] = useState(true);
  const [activePage, setActivePage] = useState("upload");

  const renderPage = () => {
    if (activePage === "dashboard") return <Dashboard />;
    if (activePage === "upload") return <MedicalReportUpload onNavigate={setActivePage} />;
    if (activePage === "matches") return <ClinicalTrials />;
  };

  return (
    <TrialDataProvider>
      {/* Splash sits on top, disappears after shutter animation */}
      {showSplash && <SplashScreen onDone={() => setShowSplash(false)} />}

      {/* Your actual app — always mounted underneath */}
      <div>
        <Navbar activePage={activePage} onNavigate={setActivePage} />
        {renderPage()}
      </div>
    </TrialDataProvider>
  );
}

export default App;