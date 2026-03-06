import React, { useState, useEffect } from 'react';
import './Dashboard.css';

const StatsRow = ({ data }) => {
  const stats = data || {
    totalTrials: 128,
    matchedTrials: 4,
    eligibilityScore: 89,
    nearbyTrials: 3
  };

  return (
    <div className="stats-row">
      <div className="stat-card">
        <div className="stat-icon icon-blue">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
        </div>
        <div className="stat-info">
          <span className="stat-label">Total Trials:</span>
          <span className="stat-value">{stats.totalTrials}</span>
        </div>
      </div>

      <div className="stat-card">
        <div className="stat-icon icon-lightblue">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
        </div>
        <div className="stat-info">
          <span className="stat-label">Matched Trials:</span>
          <span className="stat-value">{stats.matchedTrials}</span>
        </div>
      </div>

      <div className="stat-card">
        <div className="stat-icon icon-green">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
        </div>
        <div className="stat-info">
          <span className="stat-label">Eligibility Score:</span>
          <span className="stat-value text-success">{stats.eligibilityScore}%</span>
        </div>
      </div>

      <div className="stat-card">
        <div className="stat-icon icon-blue-pin">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg>
        </div>
        <div className="stat-info">
          <span className="stat-label">Nearby Trials:</span>
          <span className="stat-value">{stats.nearbyTrials}</span>
        </div>
      </div>
    </div>
  );
};

const PatientProfile = ({ data }) => {
  const patient = data || {
    age: 52,
    condition: 'Type 2 Diabetes',
    bmi: 29,
    noHeartDisease: 'Yes'
  };

  return (
    <div className="card patient-profile">
      <h2 className="card-title">Patient Profile</h2>
      
      <div className="profile-details">
        <div className="profile-row">
          <span className="profile-label">Age:</span>
          <span className="profile-value">{patient.age}</span>
        </div>
        
        <div className="profile-row">
          <span className="profile-label">Condition:</span>
          <span className="profile-value header-blue">{patient.condition}</span>
        </div>
        
        <div className="profile-row">
          <span className="profile-label">BMI:</span>
          <span className="profile-value">{patient.bmi}</span>
        </div>
        
        <div className="profile-row">
          <span className="profile-label">No Heart Disease:</span>
          <span className="profile-value text-success">{patient.noHeartDisease}</span>
        </div>
      </div>
    </div>
  );
};

const TrialMatches = ({ filters, trials }) => {
  const currentFilters = filters || {
    condition: 'Diabetes',
    distance: '< 50 km',
    phase: 'Any'
  };

  const trialList = trials || [
    {
      id: 1,
      title: 'Diabetes Medication Study',
      theme: 'blue',
      score: 92,
      status: 'Eligible',
      distance: '8 km',
      location: 'Mumbai'
    },
    {
      id: 2,
      title: 'Insulin Therapy Trial',
      theme: 'yellow',
      score: 76,
      status: 'Possible',
      distance: '15 km',
      location: 'Pune'
    },
    {
      id: 3,
      title: 'Lifestyle Intervention Study',
      theme: 'red',
      score: 45,
      status: 'Not Eligible',
      distance: '25 km',
      location: 'Delhi'
    }
  ];

  return (
    <div className="card trial-matches">
      <h2 className="card-title">Top Clinical Trial Matches</h2>
      
      <div className="filters-container">
        <div className="filter-pill">
          <span className="filter-label">Condition:</span>
          <span className="filter-value">{currentFilters.condition}</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
        </div>
        <div className="filter-pill">
          <span className="filter-label">Distance:</span>
          <span className="filter-value">{currentFilters.distance}</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
        </div>
        <div className="filter-pill">
          <span className="filter-label">Phase:</span>
          <span className="filter-value">{currentFilters.phase}</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
        </div>
      </div>

      <div className="trials-section">
        <h3 className="section-subtitle">Top Clinical Trial Matches</h3>
        <div className="trial-cards">
          {trialList.map((trial) => (
            <div key={trial.id} className={`trial-card theme-${trial.theme}`}>
              <h4 className="trial-title">{trial.title}</h4>
              <div className="trial-score-container">
                <span className="score-label">Match Score:</span>
                <span className={`score-value text-${trial.theme}`}>{trial.score}%</span>
              </div>
              <div className="progress-bar-bg">
                <div className={`progress-bar-fill fill-${trial.theme}`} style={{ width: `${trial.score}%` }}></div>
              </div>
              <p className="trial-meta">
                <strong>{trial.status}</strong> - {trial.distance} | {trial.location}
              </p>
              <button className="btn btn-primary view-details-btn">
                View Details ›
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const TrialMap = ({ locations }) => {
  const mapPins = locations || [
    { id: 1, city: 'Mumbai', top: '50%', left: '30%', color: 'red' },
    { id: 2, city: 'Delhi', top: '75%', left: '42%', color: 'red' },
    { id: 3, city: 'Pune', top: '60%', left: '55%', color: 'blue' }
  ];

  return (
    <div className="card trial-map-card">
      <h2 className="card-title-dark map-title">Trial Location Map</h2>
      <div className="map-container">
        <div className="map-background">
          {mapPins.map(pin => (
            <div 
              key={pin.id} 
              className={`map-pin pin-${pin.color}`}
              style={{ top: pin.top, left: pin.left }}
            >
              <div className="pin-icon">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
                </svg>
              </div>
              <span className="pin-label">{pin.city}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const EligibilityPanel = ({ data }) => {
  const requirements = data?.requirements || [
    { id: 1, label: 'Age 30-65', met: true },
    { id: 2, label: 'Type 2 Diabetes', met: true },
    { id: 3, label: 'BMI < 30', met: true },
    { id: 4, label: 'Slightly High (29)', met: true, warning: true },
    { id: 5, label: 'No Heart Disease', met: true }
  ];

  const readinessScore = data?.readinessScore || 85;
  const suggestions = data?.suggestions || [
    'Reduce BMI below 28',
    'Monitor blood sugar levels'
  ];

  return (
    <div className="card eligibility-panel">
      <h2 className="card-title-dark panel-title">Eligibility Breakdown</h2>
      
      <div className="requirements-list">
        {requirements.map((req) => (
          <div key={req.id} className={`requirement-item ${req.warning ? 'item-warning' : ''}`}>
            <span className="req-label">
              {req.warning && (
                <svg className="warning-icon" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2L1 21h22L12 2zm0 3.99L19.53 19H4.47L12 5.99zM11 16h2v2h-2zm0-6h2v5h-2z"/>
                </svg>
              )}
              {req.warning ? <strong>{req.label}</strong> : req.label}
            </span>
            <span className="req-status text-success">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
              {req.met ? 'Met' : 'Not Met'}
            </span>
          </div>
        ))}
      </div>

      <div className="readiness-section">
        <div className="readiness-header">
          <span className="readiness-label">Readiness Score:</span>
          <span className="readiness-value text-success">{readinessScore}%</span>
        </div>
        <div className="readiness-bar-bg">
          <div className="readiness-bar-fill bg-success" style={{ width: `${readinessScore}%` }}></div>
        </div>
      </div>

      <div className="suggestions-section">
        <h3 className="suggestions-title">Improve Eligibility:</h3>
        <ul className="suggestions-list">
          {suggestions.map((suggestion, idx) => (
            <li key={idx}>{suggestion}</li>
          ))}
        </ul>
      </div>
    </div>
  );
};

const AnalyticsOverview = ({ data }) => {
  const chartData = data || [
    { id: 'eligible', label: 'Eligible', color: '#10b981', value: 30 },
    { id: 'possible', label: 'Possible', color: '#f59e0b', value: 20 },
    { id: 'not-eligible', label: 'Not Eligible', color: '#ef4444', value: 20 },
    { id: 'other', label: 'Other', color: '#3b82f6', value: 30 }
  ];

  const total = chartData.reduce((acc, item) => acc + item.value, 0);
  let currentOffset = 0;
  
  const renderPaths = () => {
    return chartData.map((item) => {
      const percentage = (item.value / total) * 100;
      const strokeDasharray = `${percentage} 100`;
      const strokeDashoffset = -currentOffset;
      currentOffset += percentage;
      
      return (
        <path
          key={item.id}
          className="circle"
          strokeDasharray={strokeDasharray}
          strokeDashoffset={strokeDashoffset}
          stroke={item.color}
          d="M21 5.0845
            a 15.9155 15.9155 0 0 1 0 31.831
            a 15.9155 15.9155 0 0 1 0 -31.831"
        />
      );
    });
  };

  const legendData = chartData.slice(0, 3);

  return (
    <div className="card analytics-overview">
      <h2 className="card-title-dark analytics-title">Analytics Overview</h2>
      
      <h3 className="chart-subtitle">Patient Matches</h3>
      
      <div className="chart-container">
        <div className="donut-chart">
          <svg viewBox="0 0 42 42" className="circular-chart" style={{ aspectRatio: '1/1', width: '100%', height: '100%' }}>
            <path className="circle-bg"
              d="M21 5.0845
                a 15.9155 15.9155 0 0 1 0 31.831
                a 15.9155 15.9155 0 0 1 0 -31.831"
            />
            {renderPaths()}
          </svg>
        </div>
        
        <div className="chart-legend">
          {legendData.map((item) => (
            <div key={item.id} className="legend-item">
              <span className="legend-color" style={{ backgroundColor: item.color }}></span>
              <span className="legend-label">{item.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default function Dashboard() {
  const [theme, setTheme] = useState('light-theme');

  useEffect(() => {
    document.documentElement.className = theme;
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'light-theme' ? 'dark-theme' : 'light-theme');
  };

  return (
    <div className={`app-container ${theme}`}>
      <header style={{ padding: '16px 24px', display: 'flex', justifyContent: 'flex-end', backgroundColor: 'var(--card-bg)', borderBottom: '1px solid var(--border-color)' }}>
        <button onClick={toggleTheme} style={{ padding: '8px 16px', borderRadius: '4px', background: 'var(--primary-blue)', color: 'white', border: 'none', cursor: 'pointer', fontWeight: 'bold' }}>
          {theme === 'light-theme' ? '🌙 Dark Mode' : '☀️ Light Mode'}
        </button>
      </header>
      <div className="main-layout">
        <main className="content-area">
          <StatsRow />
          
          <div className="dashboard-grid">
            <div className="left-column">
              <PatientProfile />
              <TrialMatches />
              <TrialMap />
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
