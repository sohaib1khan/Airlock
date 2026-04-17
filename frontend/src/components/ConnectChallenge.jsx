import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import api from "@/utils/api";

/**
 * Layer 2 (2FA) before starting a workspace session (stub UI).
 * Requires a valid `template_id` (container template UUID) and full scope after 2FA.
 */
export function ConnectChallenge({ templateId, templateName, open, onClose, onVerified }) {
  const [challengeId, setChallengeId] = useState("");
  const [totp, setTotp] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [launchMode, setLaunchMode] = useState("resume_existing");
  const [containerPassword, setContainerPassword] = useState("");
  const [containerPasswordConfirm, setContainerPasswordConfirm] = useState("");

  useEffect(() => {
    if (!open) return;
    setChallengeId("");
    setTotp("");
    setError("");
    setBusy(false);
    setLaunchMode("resume_existing");
    setContainerPassword("");
    setContainerPasswordConfirm("");
  }, [open, templateId]);

  if (!open) return null;

  async function startChallenge() {
    setError("");
    setBusy(true);
    try {
      const { data } = await api.post("/api/auth/preconnect-challenge", { template_id: templateId });
      setChallengeId(data.challenge_id);
    } catch (err) {
      const msg = err.response?.data?.error ?? err.message ?? "Could not start challenge";
      setError(typeof msg === "string" ? msg : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function verify(e) {
    e.preventDefault();
    if (!challengeId) {
      setError("Start the challenge first");
      return;
    }
    setError("");
    setBusy(true);
    try {
      if (launchMode === "force_new") {
        if (!containerPassword) {
          setError("A sudo password is required when starting a new container");
          setBusy(false);
          return;
        }
        if (containerPassword !== containerPasswordConfirm) {
          setError("Passwords do not match");
          setBusy(false);
          return;
        }
        if (containerPassword.length < 4) {
          setError("Password must be at least 4 characters");
          setBusy(false);
          return;
        }
      }
      const { data } = await api.post("/api/auth/preconnect-verify", {
        challenge_id: challengeId,
        totp_code: totp.trim() || undefined,
      });
      onVerified?.(data.connect_token, launchMode, launchMode === "force_new" ? containerPassword : undefined);
      onClose?.();
    } catch (err) {
      const msg = err.response?.data?.error ?? err.message ?? "Verification failed";
      setError(typeof msg === "string" ? msg : "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur">
      <Card className="w-full max-w-md shadow-lg">
        <CardHeader>
          <CardTitle>Connect to workspace</CardTitle>
          <CardDescription>
            Layer 2 verification before a session starts.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Template: {templateName || "Unknown"} <span className="font-mono">({templateId})</span>
          </p>
          {!challengeId ? (
            <Button type="button" className="w-full" onClick={startChallenge} disabled={busy}>
              {busy ? "Starting…" : "Request challenge"}
            </Button>
          ) : (
            <form onSubmit={verify} className="space-y-2">
              <Label htmlFor="pc-totp">TOTP (or other 2FA methods via the API)</Label>
              <Input
                id="pc-totp"
                value={totp}
                onChange={(e) => setTotp(e.target.value)}
                placeholder="6-digit code"
                inputMode="numeric"
              />
              <div className="space-y-2 pt-2">
                <Label htmlFor="pc-launch-mode">Launch mode</Label>
                <select
                  id="pc-launch-mode"
                  value={launchMode}
                  onChange={(e) => setLaunchMode(e.target.value)}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="resume_existing">Resume existing session if present</option>
                  <option value="force_new">Force new session</option>
                </select>
              </div>
              {launchMode === "force_new" ? (
                <div className="space-y-3 rounded-md border border-border bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">
                    Set a sudo password for <span className="font-mono font-medium">kuser</span> inside
                    the new container. Use it to run <span className="font-mono">sudo apt install …</span>
                    in the terminal.
                  </p>
                  <div className="space-y-1">
                    <Label htmlFor="pc-cpw">Container sudo password</Label>
                    <Input
                      id="pc-cpw"
                      type="password"
                      value={containerPassword}
                      onChange={(e) => setContainerPassword(e.target.value)}
                      placeholder="min 4 characters"
                      autoComplete="new-password"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="pc-cpw2">Confirm password</Label>
                    <Input
                      id="pc-cpw2"
                      type="password"
                      value={containerPasswordConfirm}
                      onChange={(e) => setContainerPasswordConfirm(e.target.value)}
                      placeholder="repeat password"
                      autoComplete="new-password"
                    />
                  </div>
                </div>
              ) : null}
              {error ? <p className="text-sm text-destructive">{error}</p> : null}
              <Button type="submit" className="w-full" disabled={busy}>
                Verify &amp; get connect token
              </Button>
            </form>
          )}
        </CardContent>
        <CardFooter className="justify-end">
          <Button type="button" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
