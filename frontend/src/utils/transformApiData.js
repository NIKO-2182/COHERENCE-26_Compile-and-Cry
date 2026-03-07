/**
 * transformApiData.js
 *
 * Three focused transformers — one per GET endpoint:
 *
 *   transformSummary(json)   ← GET /results/summary
 *   transformTrials(json)    ← GET /results/trials?label=Eligible&min_score=70
 *   transformEligible(json)  ← GET /results/eligible
 *
 * Each returns a partial slice of the dashboard state object.
 * TrialDataContext merges all three via spread: { ...a, ...b, ...c }
 */

// ─── Helpers ────────────────────────────────────────────────────────────────

const fmt = (v, suffix = '') =>
  v !== null && v !== undefined ? `${v}${suffix}` : 'N/A';

const themeFromScore = (score) => {
  if (score >= 80) return 'blue';
  if (score >= 65) return 'yellow';
  return 'red';
};

const statusClsFromLabel = (label) => {
  if (label === 'Eligible')        return 'st-green';
  if (label === 'Likely Eligible') return 'st-amber';
  return 'st-red';
};

// ─── 1. GET /results/summary ─────────────────────────────────────────────────
/**
 * Returns: { statsData, patientData, metricsData }
 *
 * Expected shape from backend:
 * {
 *   patient: { patient_id, age, gender, conditions_inferred, labs: { HbA1c, Fasting_Glucose, BMI, eGFR, Creatinine } },
 *   summary: { total_trials_evaluated, eligible_count, likely_eligible_count,
 *               ineligible_count, top_score, average_score, score_distribution }
 * }
 */
export function transformSummary(json) {
  const { patient = {}, summary = {} } = json;
  const labs       = patient.labs ?? {};
  const conditions = patient.conditions_inferred ?? [];

  const statsData = {
    totalTrials:      summary.total_trials_evaluated    ?? 0,
    matchedTrials:    (summary.eligible_count ?? 0) + (summary.likely_eligible_count ?? 0),
    eligibilityScore: Math.round(summary.top_score      ?? 0),
    nearbyTrials:     summary.score_distribution?.excellent_80_plus ?? 0,
  };

  const patientData = {
    name:           `Patient ${patient.patient_id ?? '—'}`,
    age:            patient.age    ?? '—',
    gender:         patient.gender ?? '—',
    condition:      conditions.length > 0 ? conditions.join(', ') : 'Not detected',
    bmi:            fmt(labs.BMI),
    noHeartDisease: 'Unknown',
    hba1c:          fmt(labs.HbA1c,           '%'),
    egfr:           fmt(labs.eGFR,            ' mL/min'),
    creatinine:     fmt(labs.Creatinine,      ' mg/dL'),
    fastingGlucose: fmt(labs.Fasting_Glucose, ' mg/dL'),
  };

  const metricsData = {
    conditions:    conditions.length,
    labValues:     Object.values(labs).filter(v => v !== null).length,
    trialsMatched: statsData.matchedTrials,
  };

  return { statsData, patientData, metricsData };
}

// ─── 2. GET /results/trials?label=Eligible&min_score=70 ──────────────────────
/**
 * Returns: { trialsData }
 *
 * Expected shape from backend:
 * { trials: [ { rank, nct_id, title, eligibility, why_matched, why_not_matched,
 *               explanation_cards, match_breakdown, recommendation }, ... ] }
 */
export function transformTrials(json) {
  const trials = json.trials ?? json ?? [];  // backend may return array or { trials: [] }

  const trialsData = trials.slice(0, 6).map((t) => ({
    id:         t.rank,
    nctId:      t.nct_id,
    title:      t.title,
    theme:      themeFromScore(t.eligibility?.score ?? 0),
    score:      Math.round(t.eligibility?.score     ?? 0),
    band:       t.eligibility?.band                 ?? '',
    status:     t.eligibility?.label                ?? '',
    statusCls:  statusClsFromLabel(t.eligibility?.label ?? ''),
    confidence: Math.round(t.eligibility?.confidence ?? 0),
    distance:   'N/A',
    location:   'India',

    whyMatched:    (t.why_matched    ?? []).slice(0, 3).map(w => w.factor),
    whyNotMatched: (t.why_not_matched ?? []).slice(0, 2).map(w => w.factor),

    explanationCards: (t.explanation_cards ?? []).slice(0, 5),

    action:   t.recommendation?.action   ?? '',
    priority: t.recommendation?.priority ?? '',
  }));

  return { trialsData };
}

// ─── 3. GET /results/eligible ────────────────────────────────────────────────
/**
 * Returns: { eligibilityData, analyticsData }
 *
 * Expected shape: same as full payload but already filtered to eligible trials.
 * We use the top trial's match_breakdown for the eligibility checklist,
 * and the summary's score_distribution for the donut chart.
 */
export function transformEligible(json) {
  const trials  = json.trials  ?? json ?? [];
  const summary = json.summary ?? {};

  const topTrial = trials[0] ?? null;
  const mb       = topTrial?.match_breakdown ?? {};
  const labs     = json.patient?.labs ?? {};

  // ── Eligibility checklist ────────────────────────────────────────────────
  const requirements = [
    {
      id: 1,
      label: 'Age within trial range',
      met:   mb.demographics?.age_in_range ?? false,
      warn:  !(mb.demographics?.age_in_range ?? false),
      note:  `Score: ${mb.demographics?.age_score_pct ?? 'N/A'}%`,
    },
    {
      id: 2,
      label: 'Fasting Glucose available',
      met:   labs.Fasting_Glucose !== null && labs.Fasting_Glucose !== undefined,
      warn:  false,
      note:  fmt(labs.Fasting_Glucose, ' mg/dL'),
    },
    {
      id: 3,
      label: 'HbA1c available',
      met:   labs.HbA1c !== null && labs.HbA1c !== undefined,
      warn:  labs.HbA1c === null || labs.HbA1c === undefined,
      note:  labs.HbA1c ? `${labs.HbA1c}%` : 'Missing',
    },
    {
      id: 4,
      label: 'eGFR ≥ 45 mL/min',
      met:   (labs.eGFR ?? 0) >= 45,
      warn:  false,
      note:  fmt(labs.eGFR, ' mL/min'),
    },
    {
      id: 5,
      label: 'No excluded conditions',
      met:   !(mb.conditions?.has_excluded_condition ?? false),
      warn:   mb.conditions?.has_excluded_condition ?? false,
    },
    {
      id: 6,
      label: 'No excluded medications',
      met:   !(mb.conditions?.has_excluded_medication ?? false),
      warn:   mb.conditions?.has_excluded_medication ?? false,
    },
    {
      id: 7,
      label: 'Inclusion criteria covered',
      met:   (mb.criteria_coverage?.inclusion_coverage_pct ?? 0) >= 50,
      warn:  (mb.criteria_coverage?.inclusion_coverage_pct ?? 0) < 50,
      note:  `${mb.criteria_coverage?.inclusion_coverage_pct ?? 0}%`,
    },
  ];

  const issues      = topTrial?.recommendation?.issues_to_address ?? [];
  const suggestions = issues.length > 0
    ? issues.map(i => i.issue)
    : ['Upload a more detailed medical report for better matching.'];

  const eligibilityData = { requirements, suggestions };

  // ── Analytics donut (score distribution) ────────────────────────────────
  const dist = summary.score_distribution ?? {};
  const analyticsData = [
    { id: 'excellent', label: 'Excellent (80+)', color: '#10b981', value: dist.excellent_80_plus ?? 0 },
    { id: 'good',      label: 'Good (65–79)',     color: '#3b82f6', value: dist.good_65_79        ?? 0 },
    { id: 'partial',   label: 'Partial (45–64)',  color: '#f59e0b', value: dist.partial_45_64     ?? 0 },
    { id: 'weak',      label: 'Weak (25–44)',      color: '#f97316', value: dist.weak_25_44        ?? 0 },
    { id: 'poor',      label: 'Poor (<25)',        color: '#ef4444', value: dist.poor_below_25     ?? 0 },
  ].filter(d => d.value > 0);

  return { eligibilityData, analyticsData };
}