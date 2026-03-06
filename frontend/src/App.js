import { useState } from "react";
import Navbar from "./common/Navbar";

import Dashboard from "./component/Dashboard";
import MedicalReportUpload from "./component/ReportUpload";
import ClinicalTrials from "./component/Clinictrialmatch";

function App() {
  const [activePage, setActivePage] = useState("dashboard");

  const renderPage = () => {
    if (activePage === "dashboard") return <Dashboard />;
    if (activePage === "upload") return <MedicalReportUpload />;
    if (activePage === "matches") return <ClinicalTrials />;
  };

  return (
    <div>
      <Navbar activePage={activePage} onNavigate={setActivePage} />
      {renderPage()}
    </div>
  );
}

export default App;