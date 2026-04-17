import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/Spinner";
import api from "@/utils/api";

function passwordScore(password) {
  let score = 0;
  if (password.length >= 12) score += 1;
  if (/[A-Z]/.test(password)) score += 1;
  if (/[a-z]/.test(password)) score += 1;
  if (/\d/.test(password)) score += 1;
  if (/[^A-Za-z0-9]/.test(password)) score += 1;
  return Math.min(score, 4);
}

export default function SetupWizard() {
  const navigate = useNavigate();
  const [requiresSetup, setRequiresSetup] = useState(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get("/api/setup/status")
      .then((res) => setRequiresSetup(Boolean(res.data.requires_setup)))
      .catch(() => setRequiresSetup(false));
  }, []);

  const score = useMemo(() => passwordScore(password), [password]);
  const strengthLabel = ["Too weak", "Weak", "Fair", "Good", "Strong"][score] ?? "";

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    setBusy(true);
    try {
      await api.post("/api/setup/init", { username, password });
      navigate("/login", { replace: true });
    } catch (err) {
      const msg = err.response?.data?.error ?? err.message ?? "Setup failed";
      setError(typeof msg === "string" ? msg : "Setup failed");
    } finally {
      setBusy(false);
    }
  }

  if (requiresSetup === null) {
    return <Spinner label="Checking setup status…" />;
  }

  if (!requiresSetup) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="mx-auto w-full max-w-md">
      <Card>
        <CardHeader>
          <CardTitle>First-time setup</CardTitle>
          <CardDescription>
            Create the administrator account. You can add 2FA from the dashboard after setup.
          </CardDescription>
        </CardHeader>
        <form onSubmit={onSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="su-user">Username</Label>
              <Input
                id="su-user"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="su-pass">Password</Label>
              <Input
                id="su-pass"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted sm:flex-1">
                  <div
                    className="h-full rounded-full bg-primary transition-[width] duration-300"
                    style={{ width: `${(score / 4) * 100}%` }}
                  />
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">{strengthLabel}</span>
              </div>
              <p className="text-xs text-muted-foreground">
                At least 12 characters, upper and lower case, a number, and a symbol.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="su-confirm">Confirm password</Label>
              <Input
                id="su-confirm"
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>
            {error ? (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            ) : null}
          </CardContent>
          <CardFooter className="flex flex-col gap-4 sm:flex-row sm:justify-between">
            <Button type="submit" className="w-full sm:w-auto" disabled={busy}>
              {busy ? "Creating…" : "Create admin"}
            </Button>
            <Button variant="ghost" asChild className="w-full sm:w-auto">
              <Link to="/">Cancel</Link>
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
