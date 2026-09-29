import { LoaderCircle } from "lucide-react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AuthPage } from "../features/auth/AuthPage";
import { useAuth } from "../features/auth/auth-context";
import { DashboardPage } from "../pages/DashboardPage";

function ProtectedDashboard() {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="grid min-h-screen place-items-center">
        <LoaderCircle className="animate-spin text-moss-600" />
      </div>
    );
  return user ? <DashboardPage /> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage />} />
      <Route path="/" element={<ProtectedDashboard />} />
      <Route path="/employees/:employeeId" element={<ProtectedDashboard />} />
      <Route
        path="/employees/:employeeId/trips/:tripId"
        element={<ProtectedDashboard />}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
