import { useCallback, useEffect, useState } from "react";

import { MfaEnrollmentSteps } from "@/components/MfaEnrollmentSteps";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/authStore";
import api from "@/utils/api";

function methodTypeLabel(t) {
  if (t === "TOTP") return "Authenticator (TOTP)";
  if (t === "WEBAUTHN") return "Security key (WebAuthn)";
  if (t === "YUBIKEY") return "YubiKey";
  return t;
}

export default function TwoFactorManage() {
  const setUser = useAuthStore((s) => s.setUser);
  const [methods, setMethods] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editNick, setEditNick] = useState("");
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardKey, setWizardKey] = useState(0);
  const [backupBusy, setBackupBusy] = useState(false);
  const [backupCodes, setBackupCodes] = useState(null);

  const loadMethods = useCallback(async () => {
    const { data } = await api.get("/api/auth/mfa/methods");
    setMethods(Array.isArray(data) ? data : []);
    const { data: me } = await api.get("/api/auth/me");
    setUser(me);
  }, [setUser]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        await loadMethods();
      } catch (err) {
        if (!cancelled) {
          const msg = err.response?.data?.error ?? err.message ?? "Could not load 2FA methods";
          setError(typeof msg === "string" ? msg : "Could not load");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadMethods]);

  async function saveNickname(id) {
    setBusyId(id);
    setMessage("");
    setError("");
    try {
      await api.patch(`/api/auth/mfa/methods/${id}`, { nickname: editNick.trim() });
      setMessage("Label updated.");
      setEditingId(null);
      await loadMethods();
    } catch (err) {
      const d = err.response?.data;
      setError((typeof d?.error === "string" && d.error) || (typeof d?.detail === "string" && d.detail) || "Could not update");
    } finally {
      setBusyId(null);
    }
  }

  async function removeMethod(id) {
    const m = methods.find((x) => x.id === id);
    if (methods.length <= 1) {
      setError("You must keep at least one 2FA method. Add another before removing this one.");
      return;
    }
    const ok = window.confirm(
      `Remove ${methodTypeLabel(m?.method_type)} "${m?.nickname || id}"? You will need another method to sign in.`,
    );
    if (!ok) return;
    setBusyId(id);
    setMessage("");
    setError("");
    try {
      await api.delete(`/api/auth/mfa/${id}`);
      setMessage("Method removed.");
      await loadMethods();
    } catch (err) {
      const d = err.response?.data;
      setError(
        (typeof d?.error === "string" && d.error) ||
          (typeof d?.detail === "string" && d.detail) ||
          err.message ||
          "Could not remove method",
      );
    } finally {
      setBusyId(null);
    }
  }

  async function regenerateBackup() {
    const ok = window.confirm(
      "This invalidates previous backup codes and shows new ones once. Continue?",
    );
    if (!ok) return;
    setBackupBusy(true);
    setMessage("");
    setError("");
    setBackupCodes(null);
    try {
      const { data } = await api.post("/api/auth/mfa/backup/regenerate");
      setBackupCodes(data.backup_codes ?? []);
      setMessage("New backup codes generated. Save them now.");
    } catch (err) {
      const d = err.response?.data;
      setError((typeof d?.error === "string" && d.error) || "Could not regenerate codes");
    } finally {
      setBackupBusy(false);
    }
  }

  if (wizardOpen) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-2">
          <h1 className="text-xl font-semibold tracking-tight">Add 2FA method</h1>
          <Button type="button" variant="outline" size="sm" onClick={() => setWizardOpen(false)}>
            Back to list
          </Button>
        </div>
        <MfaEnrollmentSteps
          key={wizardKey}
          doneHref="/account/2fa"
          enableLimitedRedirect={false}
          onCancelWizard={() => setWizardOpen(false)}
          onDone={async () => {
            setWizardOpen(false);
            await loadMethods();
          }}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Two-factor authentication (2FA)</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your account must have at least one sign-in method. You can add several; only one is needed each time you sign in.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Registered methods</CardTitle>
          <CardDescription>Rename, remove, or add authenticators and security keys.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? <p className="text-sm text-muted-foreground">Loading…</p> : null}
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          {message ? <p className="text-sm text-emerald-600 dark:text-emerald-400">{message}</p> : null}

          {!loading && methods.length === 0 ? (
            <p className="text-sm text-muted-foreground">No methods yet. Add one below.</p>
          ) : null}

          <ul className="space-y-3">
            {methods.map((m) => (
              <li key={m.id} className="rounded-lg border border-border p-3 text-sm">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="font-medium text-foreground">{methodTypeLabel(m.method_type)}</p>
                    {editingId === m.id ? (
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                        <div className="flex-1 space-y-1">
                          <Label htmlFor={`nick-${m.id}`}>Label</Label>
                          <Input
                            id={`nick-${m.id}`}
                            value={editNick}
                            onChange={(e) => setEditNick(e.target.value)}
                            maxLength={128}
                          />
                        </div>
                        <div className="flex gap-2">
                          <Button
                            type="button"
                            size="sm"
                            disabled={busyId === m.id || !editNick.trim()}
                            onClick={() => saveNickname(m.id)}
                          >
                            Save
                          </Button>
                          <Button type="button" size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-muted-foreground">
                        <span className="text-foreground/90">{m.nickname || "—"}</span>
                        <span className="ml-2 font-mono text-xs opacity-70">{m.id.slice(0, 8)}…</span>
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground">Added {m.created_at ? new Date(m.created_at).toLocaleString() : "—"}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {editingId !== m.id ? (
                      <>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={busyId !== null}
                          onClick={() => {
                            setEditingId(m.id);
                            setEditNick(m.nickname || "");
                          }}
                        >
                          Rename
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="destructive"
                          disabled={busyId !== null || methods.length <= 1}
                          title={
                            methods.length <= 1
                              ? "Add another 2FA method before removing this one."
                              : undefined
                          }
                          onClick={() => removeMethod(m.id)}
                        >
                          Remove
                        </Button>
                      </>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>

          <Button
            type="button"
            onClick={() => {
              setWizardKey((k) => k + 1);
              setWizardOpen(true);
            }}
            className="w-full sm:w-auto"
          >
            Add method
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Backup codes</CardTitle>
          <CardDescription>One-time codes if you lose your phone or key. Regenerating invalidates old codes.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button type="button" variant="secondary" disabled={backupBusy || methods.length === 0} onClick={regenerateBackup}>
            {backupBusy ? "Working…" : "Regenerate backup codes"}
          </Button>
          {backupCodes?.length ? (
            <div className="rounded-md border border-border p-3">
              <p className="mb-2 text-xs font-medium text-muted-foreground">Save these codes now:</p>
              <ul className="grid gap-1 font-mono text-sm">
                {backupCodes.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
