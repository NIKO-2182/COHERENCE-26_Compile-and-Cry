import { useState } from "react";
import Navbar from "./common/Navbar";
import { TrialDataProvider } from "./context/TrialDataContext";
import Dashboard from "./component/Dashboard";
import MedicalReportUpload from "./component/ReportUpload";
import ClinicalTrials from "./component/AboutUs";

function App() {
  const [activePage, setActivePage] = useState("dashboard");

  const renderPage = () => {
    if (activePage === "dashboard") return <Dashboard />;
    if (activePage === "upload") return <MedicalReportUpload />;
    if (activePage === "matches") return <ClinicalTrials />;
  };

  return (
    <TrialDataProvider>
      <div>
        <Navbar activePage={activePage} onNavigate={setActivePage} />
        {renderPage()}
      </div>
    </TrialDataProvider>
  );
}

export default App;