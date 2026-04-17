import axios from "axios";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";

import { BrandMark } from "@/components/BrandMark";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/authStore";

/** Optional public repo URL (set VITE_REPO_URL when building/publishing). */
const REPO_URL = import.meta.env.VITE_REPO_URL?.trim() || "";

const HANDLE_W = 52;
const TRACK_PAD = 6;

function SlideToUnlock({ onUnlock, disabled }) {
  const trackRef = useRef(null);
  const [offset, setOffset] = useState(0);
  const offsetRef = useRef(0);
  const [dragging, setDragging] = useState(false);
  const startXRef = useRef(0);
  const startOffsetRef = useRef(0);

  const maxOffset = () => {
    const el = trackRef.current;
    if (!el) return 0;
    return Math.max(0, el.clientWidth - HANDLE_W - TRACK_PAD * 2);
  };

  const snapBack = useCallback(() => {
    setOffset(0);
    offsetRef.current = 0;
  }, []);

  const tryUnlock = useCallback(
    (current) => {
      const max = maxOffset();
      if (max <= 0) return;
      if (current / max >= 0.88) {
        onUnlock();
        setOffset(max);
        offsetRef.current = max;
        return;
      }
      snapBack();
    },
    [onUnlock, snapBack],
  );

  useEffect(() => {
    offsetRef.current = offset;
  }, [offset]);

  useEffect(() => {
    function onResize() {
      const el = trackRef.current;
      if (!el) return;
      const max = Math.max(0, el.clientWidth - HANDLE_W - TRACK_PAD * 2);
      setOffset((o) => {
        const next = Math.min(o, max);
        offsetRef.current = next;
        return next;
      });
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  function onPointerDown(e) {
    if (disabled) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    setDragging(true);
    startXRef.current = e.clientX;
    startOffsetRef.current = offsetRef.current;
  }

  function onPointerMove(e) {
    if (!dragging || disabled) return;
    const delta = e.clientX - startXRef.current;
    const max = maxOffset();
    const next = Math.max(0, Math.min(startOffsetRef.current + delta, max));
    setOffset(next);
    offsetRef.current = next;
  }

  function onPointerUp(e) {
    if (!dragging) return;
    if (e.currentTarget.hasPointerCapture?.(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    setDragging(false);
    tryUnlock(offsetRef.current);
  }

  const max = maxOffset();
  const progress = max > 0 ? offset / max : 0;

  return (
    <div
      ref={trackRef}
      className="relative h-[3.25rem] w-full select-none rounded-full border border-white/10 bg-black/25 shadow-inner backdrop-blur-sm"
      aria-label="Slide to unlock and continue to sign in"
    >
      <div
        className="pointer-events-none absolute inset-y-0 left-0 rounded-full bg-primary/15 transition-[width] duration-75"
        style={{ width: `${TRACK_PAD + offset + HANDLE_W / 2}px` }}
      />
      <span
        className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm font-medium tracking-wide text-white/35"
        style={{ opacity: Math.max(0, 1 - progress * 2.2) }}
      >
        Slide to unlock
      </span>
      <button
        type="button"
        disabled={disabled}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        className="absolute top-1 flex h-[calc(100%-0.5rem)] w-[52px] cursor-grab touch-none items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md ring-2 ring-white/20 active:cursor-grabbing disabled:cursor-not-allowed disabled:opacity-50"
        style={{ left: TRACK_PAD + offset, transition: dragging ? "none" : "left 0.2s ease-out" }}
        aria-label="Drag to unlock"
      >
        <ChevronRight className="h-6 w-6" strokeWidth={2.5} />
        <ChevronRight className="-ml-3 h-6 w-6 opacity-60" strokeWidth={2.5} />
      </button>
    </div>
  );
}

export default function Login() {
  const navigate = useNavigate();
  const setAccessToken = useAuthStore((s) => s.setAccessToken);
  const [gateOpen, setGateOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    axios
      .get("/api/auth/me", { withCredentials: true })
      .then(() => {
        if (!cancelled) navigate("/dashboard", { replace: true });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const { data } = await axios.post(
        "/api/auth/login",
        { username, password },
        { withCredentials: true },
      );
      setAccessToken(data.access_token);
      if (data.force_password_reset) {
        navigate("/account/security", { replace: true });
      } else if (data.mfa_enroll_required) {
        navigate("/mfa/enroll", { replace: true });
      } else if (data.mfa_required) {
        navigate("/mfa", { replace: true });
      } else {
        navigate("/dashboard", { replace: true });
      }
    } catch (err) {
      const msg = err.response?.data?.error ?? err.message ?? "Login failed";
      setError(typeof msg === "string" ? msg : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative min-h-[calc(100dvh-4rem)] w-full overflow-hidden px-safe pb-safe py-10 pt-[max(2.5rem,env(safe-area-inset-top,0px))]">
      {/* Ambient background */}
      <div
        className="pointer-events-none absolute inset-0 -z-10"
        aria-hidden
      >
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_120%_80%_at_50%_-20%,rgba(34,211,238,0.18),transparent_50%),radial-gradient(ellipse_80%_60%_at_100%_50%,rgba(99,102,241,0.12),transparent_45%),radial-gradient(ellipse_60%_50%_at_0%_80%,rgba(56,189,248,0.1),transparent_40%)]" />
        <div className="absolute inset-0 bg-gradient-to-b from-slate-950/80 via-slate-950 to-background" />
        <div
          className="absolute inset-0 opacity-[0.35] motion-safe:animate-[pulse_12s_ease-in-out_infinite]"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.03'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
          }}
        />
      </div>

      <div className="mx-auto flex w-full max-w-md flex-col gap-10">
        <header className="text-center">
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl border border-white/10 bg-white/5 p-2 shadow-lg backdrop-blur-md">
            <BrandMark size={48} className="drop-shadow-[0_0_12px_rgba(34,211,238,0.35)]" />
          </div>
          <h1 className="bg-gradient-to-br from-white via-cyan-100/90 to-cyan-400/80 bg-clip-text text-3xl font-semibold tracking-tight text-transparent sm:text-4xl">
            Airlock
          </h1>
          <p className="mt-2 text-sm text-muted-foreground sm:text-base">
            Secure container workspaces — sign in to continue.
          </p>
        </header>

        {!gateOpen ? (
          <div className="space-y-8">
            <div className="rounded-2xl border border-white/10 bg-card/40 p-6 shadow-xl backdrop-blur-md">
              <p className="mb-4 text-center text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                Welcome
              </p>
              <SlideToUnlock onUnlock={() => setGateOpen(true)} disabled={busy} />
              <p className="mt-4 text-center text-xs text-muted-foreground">
                Drag the handle to the right, then enter your credentials.
              </p>
            </div>
          </div>
        ) : (
          <Card className="border-white/10 bg-card/70 shadow-2xl backdrop-blur-md">
            <CardHeader className="space-y-1">
              <CardTitle className="text-xl">Sign in</CardTitle>
              <CardDescription>Enter your username and password for this Airlock instance.</CardDescription>
            </CardHeader>
            <form onSubmit={onSubmit}>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="lg-user">Username</Label>
                  <Input
                    id="lg-user"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="username"
                    autoFocus
                    required
                    className="bg-background/50"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="lg-pass">Password</Label>
                  <Input
                    id="lg-pass"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                    required
                    className="bg-background/50"
                  />
                </div>
                {error ? (
                  <p role="alert" className="text-sm text-destructive">
                    {error}
                  </p>
                ) : null}
              </CardContent>
              <CardFooter className="flex flex-col gap-3 sm:flex-row sm:justify-between">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground"
                  onClick={() => {
                    setGateOpen(false);
                    setError("");
                  }}
                >
                  ← Back to lock
                </Button>
                <Button type="submit" className="w-full sm:w-auto sm:min-w-[8rem]" disabled={busy}>
                  {busy ? "Signing in…" : "Sign in"}
                </Button>
              </CardFooter>
            </form>
          </Card>
        )}

        <footer className="text-center text-xs text-muted-foreground">
          <p className="opacity-90">Self-hosted workspace gateway — use only on networks you trust.</p>
          {REPO_URL ? (
            <p className="mt-2">
              <a
                href={REPO_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-cyan-400/90 underline decoration-cyan-500/30 underline-offset-2 transition hover:text-cyan-300 hover:decoration-cyan-400/60"
              >
                Source code
              </a>
            </p>
          ) : null}
        </footer>
      </div>
    </div>
  );
}
