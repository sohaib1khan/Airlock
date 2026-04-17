import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { BrandMark } from "@/components/BrandMark";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";
import api from "@/utils/api";

const navClass = ({ isActive }) =>
  cn(
    "inline-flex min-h-[44px] shrink-0 items-center justify-center rounded-md px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-secondary text-secondary-foreground"
      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
  );

export function AppLayout() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const accessToken = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const isAuthScreen =
    pathname === "/login" ||
    pathname === "/setup" ||
    pathname === "/mfa" ||
    pathname === "/mfa/enroll";

  async function logout() {
    try {
      await api.post("/api/auth/logout");
    } catch {
      // ignore logout API errors and clear local auth state
    }
    clear();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-safe pb-4 pt-[max(1rem,env(safe-area-inset-top,0px))] sm:flex-row sm:items-center sm:justify-between">
          <Link
            to="/"
            className="inline-flex shrink-0 items-center gap-2.5 text-lg font-semibold tracking-tight text-foreground"
            aria-label="Airlock home"
          >
            <BrandMark size={32} />
            <span>Airlock</span>
          </Link>
          {!isAuthScreen ? (
            <nav
              className="scrollbar-none -mx-1 flex min-h-[44px] flex-nowrap items-stretch gap-1 overflow-x-auto overflow-y-hidden overscroll-x-contain py-0.5 sm:mx-0 sm:flex-wrap sm:justify-end sm:overflow-visible"
              aria-label="Main"
            >
              {!accessToken ? (
                <>
                  <NavLink to="/" className={navClass} end>
                    Home
                  </NavLink>
                  <NavLink to="/setup" className={navClass}>
                    Setup
                  </NavLink>
                  <NavLink to="/login" className={navClass}>
                    Login
                  </NavLink>
                </>
              ) : (
                <>
                  <NavLink to="/dashboard" className={navClass}>
                    Dashboard
                  </NavLink>
                  {user?.is_admin ? (
                    <>
                      <NavLink
                        to="/admin/settings"
                        className={({ isActive }) =>
                          navClass({
                            isActive: isActive || pathname === "/account/2fa",
                          })
                        }
                      >
                        Admin settings
                      </NavLink>
                      <NavLink to="/admin/containers" className={navClass}>
                        Admin containers
                      </NavLink>
                    </>
                  ) : null}
                  <button
                    type="button"
                    onClick={logout}
                    className="inline-flex min-h-[44px] shrink-0 items-center justify-center rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                  >
                    Log out
                  </button>
                </>
              )}
            </nav>
          ) : null}
        </div>
      </header>
      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-safe py-6 sm:py-10">
        <Outlet />
      </div>
      <footer className="border-t border-border px-safe pb-safe pt-6 text-center text-xs text-muted-foreground">
        Self-hosted workspace access · Use only on networks you trust
      </footer>
    </div>
  );
}
