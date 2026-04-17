import { useAuthStore } from "@/store/authStore";
import api from "@/utils/api";
import { useNavigate } from "react-router-dom";

import { AuthGuard } from "@/components/AuthGuard";
import { MfaEnrollmentSteps } from "@/components/MfaEnrollmentSteps";

export default function MfaEnroll() {
  const navigate = useNavigate();
  const clear = useAuthStore((s) => s.clear);

  async function signOut() {
    try {
      await api.post("/api/auth/logout");
    } catch {
      // ignore
    }
    clear();
    navigate("/login", { replace: true });
  }

  return (
    <AuthGuard requireFullScope={false} redirectIfFullTo="/account/2fa">
      <div className="py-4">
        <MfaEnrollmentSteps doneHref="/dashboard" enableLimitedRedirect onSignOut={signOut} />
      </div>
    </AuthGuard>
  );
}
