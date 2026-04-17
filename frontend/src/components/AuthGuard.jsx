import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Spinner } from "@/components/Spinner";
import { useAuthStore } from "@/store/authStore";
import api from "@/utils/api";

/**
 * @param {object} props
 * @param {import('react').ReactNode} props.children
 * @param {boolean} [props.requireFullScope=true] If true, users with limited scope (pending 2FA) go to /mfa
 * @param {string | null} [props.redirectIfFullTo=null] If set and user already has full scope, redirect (e.g. /mfa page -> /dashboard)
 */
export function AuthGuard({ children, requireFullScope = true, redirectIfFullTo = null }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const setUser = useAuthStore((s) => s.setUser);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function verify() {
      try {
        const { data } = await api.get("/api/auth/me");
        if (cancelled) return;
        setUser(data);
        if (requireFullScope && data.scope === "limited") {
          if (pathname === "/account/security" && data.force_password_reset) {
            setReady(true);
            return;
          }
          if (data.mfa_enrollment_required) {
            navigate("/mfa/enroll", { replace: true });
          } else {
            navigate("/mfa", { replace: true });
          }
          return;
        }
        if (redirectIfFullTo && data.scope === "full") {
          navigate(redirectIfFullTo, { replace: true });
          return;
        }
        setReady(true);
      } catch {
        if (!cancelled) navigate("/login", { replace: true });
      }
    }
    verify();
    return () => {
      cancelled = true;
    };
  }, [navigate, pathname, setUser, requireFullScope, redirectIfFullTo]);

  if (!ready) {
    return <Spinner label="Checking session…" />;
  }

  return children;
}
