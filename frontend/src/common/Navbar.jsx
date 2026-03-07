import { useState, useRef, useEffect } from "react";
import "./Navbar.css";

const NAV_ITEMS = [
  { id: "dashboard",  label: "Dashboard",     icon: "⊞" },
  { id: "upload",     label: "Upload Report",  icon: "↑" },
  { id: "matches",    label: "About Us", icon: "◎" },
];

export default function Navbar({ activePage = "dashboard", onNavigate }) {
  const [menuOpen, setMenuOpen]       = useState(false);
  const [prevPage, setPrevPage]       = useState(null);
  const [transitioning, setTransitioning] = useState(false);
  const timeoutRef = useRef(null);

  const handleNavigate = (id) => {
    if (id === activePage) return;
    setPrevPage(activePage);
    setTransitioning(true);
    onNavigate(id);
    clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setTransitioning(false), 400);
    setMenuOpen(false);
  };

  useEffect(() => () => clearTimeout(timeoutRef.current), []);

  return (
    <>
      <nav className="navbar">
        <div className="navbar-inner">

          {/* ── Logo ── */}
          <div className="nav-logo" onClick={() => handleNavigate("dashboard")}>
            <div className="nav-logo-mark">
              <svg width="17" height="17" viewBox="0 0 20 20" fill="none">
                <path
                  d="M10 2L3 6v4c0 4 3.1 7.7 7 8.9C13.9 17.7 17 14 17 10V6l-7-4z"
                  stroke="white"
                  strokeWidth="1.7"
                  strokeLinejoin="round"
                />
                <circle cx="10" cy="10" r="2" fill="white" opacity="0.75" />
              </svg>
            </div>

            <div className="nav-logo-text">
              <span className="nav-logo-name">
                Nex<span>Trial</span>
              </span>
              <span className="nav-logo-sub">AI · Clinical Intelligence</span>
            </div>
          </div>

          {/* ── Desktop Links ── */}
          <ul className="nav-links">
            {NAV_ITEMS.map((item) => {
              const isActive = activePage === item.id;
              const isTransitioning = transitioning && isActive;
              return (
                <li key={item.id}>
                  <button
                    className={[
                      "nav-link",
                      isActive ? "nav-link--active" : "",
                      isTransitioning ? "nav-link--transitioning" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    onClick={() => handleNavigate(item.id)}
                    aria-current={isActive ? "page" : undefined}
                  >
                    <span className="nav-link-icon">{item.icon}</span>
                    {item.label}
                    {isActive && <span className="nav-link-bar" key={activePage} />}
                  </button>
                </li>
              );
            })}
          </ul>

          {/* ── Hamburger (mobile only) ── */}
          <button
            className={`nav-hamburger ${menuOpen ? "is-open" : ""}`}
            onClick={() => setMenuOpen((v) => !v)}
            aria-label="Toggle menu"
          >
            <span />
            <span />
            <span />
          </button>

        </div>
      </nav>

      {/* ── Mobile Drawer ── */}
      <div className={`nav-drawer ${menuOpen ? "nav-drawer--open" : ""}`}>
        <ul className="nav-drawer-links">
          {NAV_ITEMS.map((item) => (
            <li key={item.id}>
              <button
                className={`nav-drawer-link ${
                  activePage === item.id ? "nav-drawer-link--active" : ""
                }`}
                onClick={() => handleNavigate(item.id)}
              >
                <span className="drawer-icon">{item.icon}</span>
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      </div>

      {menuOpen && (
        <div className="nav-overlay" onClick={() => setMenuOpen(false)} />
      )}
    </>
  );
}