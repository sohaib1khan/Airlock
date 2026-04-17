import { startAuthentication } from "@simplewebauthn/browser";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { AuthGuard } from "@/components/AuthGuard";
import { Button } from "@/components/ui/button";
import { isWebAuthnAvailable, webAuthnUnavailableExplanation } from "@/lib/webAuthnEnv";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/authStore";
import api from "@/utils/api";

function formatVerifyError(err) {
  const d = err.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d
      .map((x) => (typeof x?.msg === "string" ? x.msg : JSON.stringify(x)))
      .filter(Boolean)
      .join(" ");
  }
  const e = err.response?.data?.error;
  if (typeof e === "string") return e;
  return err.message ?? "Verification failed";
}

function MFAForm() {
  const navigate = useNavigate();
  const setAccessToken = useAuthStore((s) => s.setAccessToken);
  const user = useAuthStore((s) => s.user);
  const [totp, setTotp] = useState("");
  const [backup, setBackup] = useState("");
  const [yubi, setYubi] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [webAuthnBusy, setWebAuthnBusy] = useState(false);

  const hints = user?.mfa_hints;
  const showTotp = hints ? hints.totp : true;
  const showBackup = hints ? hints.backup : true;
  const showYubi = hints ? hints.yubikey_otp : true;
  const showWebAuthn = hints ? hints.webauthn : true;

  const description = useMemo(() => {
    if (!hints) {
      return "Use one of your enrolled methods below. If an option does not apply to your account, ignore it.";
    }
    const parts = [];
    if (hints.totp) parts.push("authenticator code");
    if (hints.backup) parts.push("backup code");
    if (hints.yubikey_otp) parts.push("YubiKey OTP");
    if (hints.webauthn) parts.push("security key");
    if (parts.length === 0) {
      return "No second-factor methods are available for this session. Contact an administrator.";
    }
    if (parts.length === 1) {
      return `Use your ${parts[0]} to finish signing in.`;
    }
    const last = parts.pop();
    return `Use any one enrolled method: ${parts.join(", ")}, or ${last}.`;
  }, [hints]);

  async function submit(payload) {
    setError("");
    setBusy(true);
    try {
      const { data } = await api.post("/api/auth/mfa/verify", payload);
      setAccessToken(data.access_token);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(formatVerifyError(err));
    } finally {
      setBusy(false);
    }
  }

  function onSubmitTotp(e) {
    e.preventDefault();
    submit({ totp_code: totp.trim() });
  }

  function onSubmitBackup(e) {
    e.preventDefault();
    submit({ backup_code: backup.trim() });
  }

  function onSubmitYubi(e) {
    e.preventDefault();
    submit({ yubikey_otp: yubi.trim() });
  }

  async function onWebAuthn() {
    setError("");
    if (!isWebAuthnAvailable()) {
      setError(webAuthnUnavailableExplanation() ?? "WebAuthn is not available in this environment.");
      return;
    }
    setWebAuthnBusy(true);
    try {
      const { data: opts } = await api.post("/api/auth/mfa/webauthn/authenticate/begin");
      const asseResp = await startAuthentication({ optionsJSON: opts });
      const { data } = await api.post("/api/auth/mfa/verify", { webauthn: asseResp });
      setAccessToken(data.access_token);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      const msg = err?.message && typeof err.message === "string" ? err.message : "";
      if (msg.includes("WebAuthn is not supported")) {
        setError(webAuthnUnavailableExplanation() ?? formatVerifyError(err));
      } else {
        setError(formatVerifyError(err));
      }
    } finally {
      setWebAuthnBusy(false);
    }
  }

  const webAuthnUsable = isWebAuthnAvailable();
  const disableInputs = busy || webAuthnBusy;

  const hasAnyOption =
    !hints || showTotp || showBackup || showYubi || showWebAuthn;

  return (
    <Card className="mx-auto w-full max-w-md">
      <CardHeader>
        <CardTitle>Two-factor authentication (2FA)</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {!hasAnyOption ? (
          <p className="text-sm text-muted-foreground">
            You can try signing out and signing in again, or contact support if this persists.
          </p>
        ) : null}

        {showTotp ? (
          <form onSubmit={onSubmitTotp} className="space-y-2">
            <Label htmlFor="mfa-totp">Authenticator (TOTP)</Label>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                id="mfa-totp"
                value={totp}
                onChange={(e) => setTotp(e.target.value)}
                placeholder="6-digit code"
                autoComplete="one-time-code"
                inputMode="numeric"
              />
              <Button type="submit" disabled={disableInputs}>
                Verify
              </Button>
            </div>
          </form>
        ) : null}

        {showBackup ? (
          <form onSubmit={onSubmitBackup} className="space-y-2">
            <Label htmlFor="mfa-backup">Backup code</Label>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                id="mfa-backup"
                value={backup}
                onChange={(e) => setBackup(e.target.value)}
                placeholder="xxxx-xxxx"
              />
              <Button type="submit" variant="secondary" disabled={disableInputs}>
                Use backup
              </Button>
            </div>
          </form>
        ) : null}

        {showYubi ? (
          <form onSubmit={onSubmitYubi} className="space-y-2">
            <Label htmlFor="mfa-yubi">YubiKey OTP</Label>
            <p className="text-xs text-muted-foreground">
              Touch the key so it types a 44-character code, then paste it here.
            </p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                id="mfa-yubi"
                value={yubi}
                onChange={(e) => setYubi(e.target.value.replace(/\s/g, ""))}
                placeholder="44-character touch OTP"
                autoComplete="off"
                spellCheck={false}
                className="font-mono text-sm"
                maxLength={44}
              />
              <Button type="submit" variant="secondary" disabled={disableInputs}>
                Verify YubiKey
              </Button>
            </div>
          </form>
        ) : null}

        {showWebAuthn ? (
          <div className="space-y-2">
            <Label htmlFor="mfa-webauthn-btn">Security key (WebAuthn)</Label>
            {webAuthnUsable ? (
              <p className="text-xs text-muted-foreground">Use a registered FIDO2 / security key when prompted.</p>
            ) : (
              <p className="rounded-md border border-amber-500/35 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-100/95">
                {webAuthnUnavailableExplanation()}
              </p>
            )}
            <Button
              id="mfa-webauthn-btn"
              type="button"
              variant="outline"
              className="w-full"
              disabled={disableInputs || !webAuthnUsable}
              title={!webAuthnUsable ? webAuthnUnavailableExplanation() ?? undefined : undefined}
              onClick={onWebAuthn}
            >
              {webAuthnBusy ? "Waiting for key…" : "Use security key"}
            </Button>
          </div>
        ) : null}

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
      </CardContent>
      <CardFooter className="flex flex-col gap-2 border-t border-border pt-6 sm:flex-row sm:justify-between">
        <Button variant="ghost" asChild>
          <Link to="/login">Back to login</Link>
        </Button>
      </CardFooter>
    </Card>
  );
}

export default function MFAChallenge() {
  return (
    <AuthGuard requireFullScope={false} redirectIfFullTo="/dashboard">
      <div className="py-4">
        <MFAForm />
      </div>
    </AuthGuard>
  );
}
