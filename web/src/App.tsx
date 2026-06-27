import { lazy, Suspense, useEffect, useState } from "react"; // useEffect/useState used in RootRedirect
import { Routes, Route, useNavigate, useLocation } from "react-router-dom";
import HomePage from "./pages/HomePage";
import RaceDetailPage from "./pages/RaceDetailPage";
import HorsePage from "./pages/HorsePage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import FavoritesPage from "./pages/FavoritesPage";
import ROIReportPage from "./pages/ROIReportPage";
import NotFoundPage from "./pages/NotFoundPage";
import { BottomNav } from "./components/BottomNav";
import { fetchLatestRaceDate } from "./api/races";

const MlMonitoringPage = lazy(() => import("./pages/admin/MlMonitoringPage"));
const DataManagementPage = lazy(() => import("./pages/admin/DataManagementPage"));

function RootRedirect() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchLatestRaceDate()
      .then((date) => navigate(`/races/${date}`, { replace: true }))
      .catch(() => {
        const today = new Date().toISOString().split("T")[0];
        navigate(`/races/${today}`, { replace: true });
      })
      .finally(() => setLoading(false));
  }, [navigate]);

  if (loading) return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center">
      <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );
  return null;
}

const HIDE_NAV = ["/login", "/register", "/admin"];

function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const hideNav = HIDE_NAV.some((p) => pathname.startsWith(p));
  return (
    <>
      {children}
      {!hideNav && <BottomNav />}
    </>
  );
}

function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <Layout>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/races" element={<RootRedirect />} />
          <Route path="/races/:date" element={<HomePage />} />
          <Route path="/races/:date/:raceId" element={<RaceDetailPage />} />
          <Route path="/horses/:horseId" element={<HorsePage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
          <Route path="/reports/roi" element={<ROIReportPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route
            path="/admin/ml"
            element={
              <Suspense fallback={<div className="p-4 text-slate-400">Loading...</div>}>
                <MlMonitoringPage />
              </Suspense>
            }
          />
          <Route
            path="/admin/data"
            element={
              <Suspense fallback={<div className="p-4 text-slate-400">Loading...</div>}>
                <DataManagementPage />
              </Suspense>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Layout>
    </div>
  );
}

export default App;
