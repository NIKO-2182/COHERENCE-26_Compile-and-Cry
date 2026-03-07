/**
 * TrialDataContext.jsx  — UPDATED
 *
 * Changes from previous version:
 *  1. localStorage persistence — trialData is saved after every successful
 *     fetchDashboardData call and rehydrated automatically on page refresh.
 *  2. 24-hour TTL — stale data is discarded silently on mount.
 *  3. setTrialData exposed in context value so Dashboard can also write to it
 *     if needed (e.g. for external rehydration or testing).
 *  4. All existing API logic (fetchDashboardData, refreshData) is unchanged.
 */

import { createContext, useContext, useState, useCallback } from "react";
import { transformSummary, transformTrials, transformEligible } from "../utils/transformApiData";

const TrialDataContext = createContext(null);

export const BASE_URL = "http://192.168.137.226:8000";

/* ─── localStorage helpers ────────────────────────────────────
   Key   : "nex_trial_dashboard_data"
   Value : { data: <trialData>, ts: <epoch ms> }
   TTL   : 24 hours — after that the entry is ignored and removed
──────────────────────────────────────────────────────────────── */
const STORAGE_KEY = "nex_trial_dashboard_data";
const TTL_MS      = 24 * 60 * 60 * 1000; // 24 hours

function persistData(data) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ data, ts: Date.now() }));
  } catch (e) {
    // Quota exceeded or private-browsing restriction — fail silently
    console.warn("Could not persist trial data to localStorage:", e);
  }
}

function loadPersistedData() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const { data, ts } = JSON.parse(raw);
    if (Date.now() - ts > TTL_MS) {
      localStorage.removeItem(STORAGE_KEY); // expired — clean up
      return null;
    }
    return data;
  } catch {
    return null;
  }
}

function clearPersistedData() {
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
}

/* ─── Provider ─────────────────────────────────────────────── */
export function TrialDataProvider({ children }) {
  // Initialise from localStorage immediately — no flash of empty dashboard on refresh
  const [trialData, setTrialDataState] = useState(() => loadPersistedData());
  const [isLoading, setIsLoading]      = useState(false);
  const [error, setError]              = useState(null);

  /**
   * Wrapper around setState that also writes through to localStorage.
   * Passing null clears both state and storage (e.g. on logout / new upload).
   */
  const setTrialData = useCallback((data) => {
    setTrialDataState(data);
    if (data) {
      persistData(data);
    } else {
      clearPersistedData();
    }
  }, []);

  /**
   * Called from ReportUpload once the PDF upload finishes.
   * Hits all three GET endpoints in parallel and merges into one state object.
   */
  const fetchDashboardData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [summaryRes, trialsRes, eligibleRes] = await Promise.all([
        fetch(`${BASE_URL}/results/summary`),
        fetch(`${BASE_URL}/results/trials?label=Eligible&min_score=70`),
        fetch(`${BASE_URL}/results/eligible`),
      ]);

      const [summaryJson, trialsJson, eligibleJson] = await Promise.all([
        summaryRes.json(),
        trialsRes.json(),
        eligibleRes.json(),
      ]);

      const merged = {
        ...transformSummary(summaryJson),   // → statsData, patientData, metricsData
        ...transformTrials(trialsJson),     // → trialsData
        ...transformEligible(eligibleJson), // → eligibilityData, analyticsData
      };

      // setTrialData persists to localStorage automatically
      setTrialData(merged);
    } catch (err) {
      console.error("Dashboard fetch failed:", err);
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [setTrialData]);

  /**
   * Hits GET /results/refresh (hot-reload after Mod3 reruns) then re-fetches.
   */
  const refreshData = useCallback(async () => {
    try {
      await fetch(`${BASE_URL}/results/refresh`);
      await fetchDashboardData();
    } catch (err) {
      console.error("Refresh failed:", err);
    }
  }, [fetchDashboardData]);

  return (
    <TrialDataContext.Provider
      value={{ trialData, setTrialData, isLoading, error, fetchDashboardData, refreshData }}
    >
      {children}
    </TrialDataContext.Provider>
  );
}

export function useTrialData() {
  const ctx = useContext(TrialDataContext);
  if (!ctx) throw new Error("useTrialData must be used inside <TrialDataProvider>");
  return ctx;
}