import axios from "axios";
import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "@/components/AppLayout";
import { AdminGuard } from "@/components/AdminGuard";
import { AuthGuard } from "@/components/AuthGuard";
import { Spinner } from "@/components/Spinner";
import AccountSecurityPage from "@/pages/AccountSecurity";
import Dashboard from "@/pages/Dashboard";
import Login from "@/pages/Login";
import MFAChallenge from "@/pages/MFAChallenge";
import MfaEnroll from "@/pages/MfaEnroll";
import TwoFactorManage from "@/pages/account/TwoFactorManage";
import WorkspaceSessionPage from "@/pages/WorkspaceSession";
import AuditLogsPage from "@/pages/admin/AuditLogs";
import AdminSettingsPage from "@/pages/admin/AdminSettings";
import ContainerTemplatesAdmin from "@/pages/admin/ContainerTemplates";
import AdminUsersPage from "@/pages/admin/AdminUsers";
import SetupWizard from "@/pages/SetupWizard";

function Home() {
  const [requiresSetup, setRequiresSetup] = useState(null);

  useEffect(() => {
    axios
      .get("/api/setup/status", { withCredentials: true })
      .then((res) => setRequiresSetup(Boolean(res.data.requires_setup)))
      .catch(() => setRequiresSetup(false));
  }, []);

  if (requiresSetup === null) {
    return <Spinner label="Starting…" />;
  }

  return <Navigate to={requiresSetup ? "/setup" : "/login"} replace />;
}

function DashboardGate() {
  return (
    <AuthGuard>
      <Dashboard />
    </AuthGuard>
  );
}

function SessionGate() {
  return (
    <AuthGuard>
      <WorkspaceSessionPage />
    </AuthGuard>
  );
}

function AccountSecurityGate() {
  return (
    <AuthGuard>
      <AccountSecurityPage />
    </AuthGuard>
  );
}

function TwoFactorManageGate() {
  return (
    <AuthGuard>
      <div className="py-4">
        <TwoFactorManage />
      </div>
    </AuthGuard>
  );
}

function AdminContainersGate() {
  return (
    <AdminGuard>
      <ContainerTemplatesAdmin />
    </AdminGuard>
  );
}

function AdminSettingsGate() {
  return (
    <AdminGuard>
      <AdminSettingsPage />
    </AdminGuard>
  );
}

function AdminUsersGate() {
  return (
    <AdminGuard>
      <AdminUsersPage />
    </AdminGuard>
  );
}

function AuditLogsGate() {
  return (
    <AdminGuard>
      <AuditLogsPage />
    </AdminGuard>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Home />} />
        <Route path="/setup" element={<SetupWizard />} />
        <Route path="/login" element={<Login />} />
        <Route path="/mfa" element={<MFAChallenge />} />
        <Route path="/mfa/enroll" element={<MfaEnroll />} />
        <Route path="/dashboard" element={<DashboardGate />} />
        <Route path="/account/security" element={<AccountSecurityGate />} />
        <Route path="/account/2fa" element={<TwoFactorManageGate />} />
        <Route path="/session/:sessionId" element={<SessionGate />} />
        <Route path="/admin/settings" element={<AdminSettingsGate />} />
        <Route path="/admin/users" element={<AdminUsersGate />} />
        <Route path="/admin/audit-logs" element={<AuditLogsGate />} />
        <Route path="/admin/containers" element={<AdminContainersGate />} />
      </Route>
    </Routes>
  );
}
