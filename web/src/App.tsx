import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import HomePage from "./pages/HomePage";
import RaceDetailPage from "./pages/RaceDetailPage";
import HorsePage from "./pages/HorsePage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import FavoritesPage from "./pages/FavoritesPage";
import NotFoundPage from "./pages/NotFoundPage";

const MlMonitoringPage = lazy(() => import("./pages/admin/MlMonitoringPage"));
const DataManagementPage = lazy(() => import("./pages/admin/DataManagementPage"));

function App() {
  const today = new Date().toISOString().split("T")[0];
  return (
    <div className="min-h-screen bg-gray-50 text-slate-900">
      <Routes>
        <Route path="/" element={<Navigate to={`/races/${today}`} replace />} />
        <Route path="/races/:date" element={<HomePage />} />
        <Route path="/races/:date/:raceId" element={<RaceDetailPage />} />
        <Route path="/horses/:horseId" element={<HorsePage />} />
        <Route path="/favorites" element={<FavoritesPage />} />
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
    </div>
  );
}

export default App;
