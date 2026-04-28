import { AuthProvider } from "../context/AuthContext";
import AuthGate from "../auth/AuthGate";
import Dashboard from "../Dashboard";

export default function AuthenticatedDashboardRoute() {
  return (
    <AuthProvider>
      <AuthGate>
        <Dashboard />
      </AuthGate>
    </AuthProvider>
  );
}
