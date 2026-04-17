import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Spinner } from "@/components/Spinner";
import { useAuthStore } from "@/store/authStore";
import api from "@/utils/api";

export function AdminGuard({ children }) {
  const navigate = useNavigate();
  const setUser = useAuthStore((s) => s.setUser);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function verifyAdmin() {
      try {
        const { data } = await api.get("/api/auth/me");
        if (cancelled) return;
        setUser(data);
        if (data.scope !== "full") {
          if (data.mfa_enrollment_required) {
            navigate("/mfa/enroll", { replace: true });
          } else {
            navigate("/mfa", { replace: true });
          }
          return;
        }
        if (!data.is_admin) {
          navigate("/dashboard", { replace: true });
          return;
        }
        setReady(true);
      } catch {
        if (!cancelled) navigate("/login", { replace: true });
      }
    }
    verifyAdmin();
    return () => {
      cancelled = true;
    };
  }, [navigate, setUser]);

  if (!ready) {
    return <Spinner label="Checking admin access…" />;
  }
  return children;
}
