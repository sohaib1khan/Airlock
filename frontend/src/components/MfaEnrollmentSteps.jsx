import { startRegistration } from "@simplewebauthn/browser";
import { QRCodeSVG } from "qrcode.react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { isWebAuthnAvailable, webAuthnUnavailableExplanation } from "@/lib/webAuthnEnv";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/authStore";
import api from "@/utils/api";

/**
 * Shared TOTP + WebAuthn enrollment flows (first factor or additional methods).
 *
 * @param {object} props
 * @param {string} [props.doneHref="/dashboard"] Where "Done" links go after success.
 * @param {boolean} [props.enableLimitedRedirect=true] Redirect to /mfa if session is limited but user already has MFA (wrong screen).
 * @param {() => void} [props.onSignOut] Shown when 2FA enrollment is required (limited session, no factors yet).
 * @param {() => void} [props.onCancelWizard] When set, show "Cancel" on the method picker (e.g. return to 2FA manage list).
 * @param {() => void} [props.onDone] When set, "Done" buttons call this instead of navigating (e.g. close wizard on manage page).
 */
export function MfaEnrollmentSteps({
  doneHref = "/dashboard",
  enableLimitedRedirect = true,
  onSignOut,
  onCancelWizard,
  onDone,
}) {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const setAccessToken = useAuthStore((s) => s.setAccessToken);
  const setUser = useAuthStore((s) => s.setUser);

  const [step, setStep] = useState("menu");
  const [methodId, setMethodId] = useState("");
  const [otpauthUri, setOtpauthUri] = useState("");
  const [confirmCode, setConfirmCode] = useState("");
  const [backupCodes, setBackupCodes] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [webBusy, setWebBusy] = useState(false);
  const [yubikeyOtpAvailable, setYubikeyOtpAvailable] = useState(false);
  const [yubiOtp, setYubiOtp] = useState("");

  useEffect(() => {
    if (!enableLimitedRedirect) return;
    if (user && user.scope === "limited" && user.mfa_enrolled) {
      navigate("/mfa", { replace: true });
    }
  }, [user, navigate, enableLimitedRedirect]);

  useEffect(() => {
    let cancelled = false;
    if (step !== "menu") return;
    (async () => {
      try {
        const { data } = await api.get("/api/auth/mfa/enrollment-capabilities");
        if (!cancelled && data?.yubikey_otp) setYubikeyOtpAvailable(true);
      } catch {
        if (!cancelled) setYubikeyOtpAvailable(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [step]);

  async function refreshMe() {
    const { data } = await api.get("/api/auth/me");
    setUser(data);
  }

  async function beginTotp() {
    setError("");
    setBusy(true);
    try {
      const { data } = await api.post("/api/auth/mfa/totp/begin");
      setMethodId(data.method_id);
      setOtpauthUri(data.otpauth_uri);
      setStep("totp-qr");
    } catch (err) {
      const msg = err.response?.data?.error ?? err.message ?? "Failed";
      setError(typeof msg === "string" ? msg : "Failed");
    } finally {
      setBusy(false);
    }
  }

  async function confirmTotp(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const { data } = await api.post("/api/auth/mfa/totp/confirm", {
        method_id: methodId,
        code: confirmCode.trim(),
      });
      if (data.access_token) {
        setAccessToken(data.access_token);
        await refreshMe();
      }
      setBackupCodes(data.backup_codes ?? []);
      setStep("totp-done");
    } catch (err) {
      const msg = err.response?.data?.error ?? err.message ?? "Invalid code";
      setError(typeof msg === "string" ? msg : "Invalid code");
    } finally {
      setBusy(false);
    }
  }

  async function submitYubikeyEnroll(e) {
    e.preventDefault();
    const otp = yubiOtp.trim();
    if (otp.length !== 44) {
      setError("Paste the full 44-character code from your YubiKey.");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const { data } = await api.post("/api/auth/mfa/yubikey/enroll", { otp });
      if (data.access_token) {
        setAccessToken(data.access_token);
        await refreshMe();
      }
      setBackupCodes(data.backup_codes ?? []);
      setYubiOtp("");
      setStep("totp-done");
    } catch (err) {
      const msg = err.response?.data?.detail ?? err.response?.data?.error ?? err.message ?? "Enrollment failed";
      const s = typeof msg === "string" ? msg : Array.isArray(msg) ? msg.map((x) => x.msg).join(" ") : "Enrollment failed";
      setError(s);
    } finally {
      setBusy(false);
    }
  }

  async function registerWebAuthn() {
    setError("");
    if (!isWebAuthnAvailable()) {
      setError(webAuthnUnavailableExplanation() ?? "WebAuthn is not available here.");
      return;
    }
    setWebBusy(true);
    try {
      const { data: opts } = await api.post("/api/auth/mfa/webauthn/register/begin");
      const attResp = await startRegistration({ optionsJSON: opts });
      const { data } = await api.post("/api/auth/mfa/webauthn/register/finish", { credential: attResp });
      if (data.access_token) {
        setAccessToken(data.access_token);
        await refreshMe();
      }
      if (data.backup_codes?.length) {
        setBackupCodes(data.backup_codes);
        setStep("totp-done");
      } else {
        setStep("webauthn-done");
      }
    } catch (err) {
      const raw = err.response?.data?.detail ?? err.response?.data?.error ?? err.message ?? "Registration failed";
      const msg = typeof raw === "string" ? raw : "Registration failed";
      if (msg === "WebAuthn is not supported in this browser" || msg.includes("WebAuthn is not supported")) {
        setError(webAuthnUnavailableExplanation() ?? msg);
      } else {
        setError(msg);
      }
    } finally {
      setWebBusy(false);
    }
  }

  const webAuthnUsable = isWebAuthnAvailable();
  const webAuthnHint = webAuthnUnavailableExplanation();

  const required = Boolean(user?.mfa_enrollment_required);
  const hasMfa = Boolean(user?.mfa_enrolled);
  const showSignOut = required && typeof onSignOut === "function";

  if (step === "menu") {
    return (
      <Card className="mx-auto w-full max-w-lg">
        <CardHeader>
          <CardTitle>
            {required ? "Set up 2FA (required)" : hasMfa ? "Add another sign-in method" : "Add two-factor authentication (2FA)"}
          </CardTitle>
          <CardDescription>
            {required
              ? "This instance requires two-factor authentication (2FA). Enroll at least one option. You can add more for backup — only one is needed to sign in."
              : hasMfa
                ? "Add a backup authenticator or security key. At sign-in, any one enrolled 2FA method works."
                : "Choose how you want to protect your account with 2FA."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <Button type="button" onClick={beginTotp} disabled={busy}>
            {busy ? "Starting…" : "Authenticator app (TOTP)"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={registerWebAuthn}
            disabled={webBusy || !webAuthnUsable}
            title={!webAuthnUsable ? webAuthnHint ?? undefined : undefined}
          >
            {webBusy ? "Waiting for key…" : "Security key (WebAuthn / FIDO2)"}
          </Button>
          {!webAuthnUsable && webAuthnHint ? (
            <p className="rounded-md border border-amber-500/35 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-100/95">
              {webAuthnHint}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              Includes YubiKey and other keys in FIDO2 / WebAuthn mode (needs HTTPS or localhost).
            </p>
          )}
          {yubikeyOtpAvailable ? (
            <>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setError("");
                  setYubiOtp("");
                  setStep("yubikey-otp");
                }}
                disabled={busy}
              >
                YubiKey (44-character OTP)
              </Button>
              <p className="text-xs text-muted-foreground">
                For YubiKeys programmed with Yubico OTP (touch to type a one-time password). Requires YubiCloud API
                keys on the server.
              </p>
            </>
          ) : null}
        </CardContent>
        <CardFooter className="flex flex-wrap gap-2">
          {showSignOut ? (
            <Button type="button" variant="ghost" onClick={onSignOut}>
              Sign out
            </Button>
          ) : null}
          {onCancelWizard ? (
            <Button type="button" variant="ghost" onClick={onCancelWizard}>
              Cancel
            </Button>
          ) : null}
          {!showSignOut && !onCancelWizard ? (
            <Button variant="ghost" asChild>
              <Link to="/dashboard">Back to dashboard</Link>
            </Button>
          ) : null}
        </CardFooter>
      </Card>
    );
  }

  if (step === "yubikey-otp") {
    return (
      <Card className="mx-auto w-full max-w-lg">
        <CardHeader>
          <CardTitle>Enroll YubiKey OTP</CardTitle>
          <CardDescription>
            Focus a text field, then touch the YubiKey so it types a 44-character code. Paste that code here. Your
            server must have YubiCloud API credentials configured.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submitYubikeyEnroll} className="space-y-3">
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            <div className="space-y-2">
              <Label htmlFor="enroll-yubi-otp">YubiKey OTP (44 characters)</Label>
              <Input
                id="enroll-yubi-otp"
                value={yubiOtp}
                onChange={(e) => setYubiOtp(e.target.value.replace(/\s/g, ""))}
                autoComplete="off"
                spellCheck={false}
                className="font-mono text-sm"
                placeholder="ccccccccc…"
                maxLength={44}
              />
            </div>
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Verifying…" : "Confirm enrollment"}
            </Button>
          </form>
        </CardContent>
        <CardFooter className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setError("");
              setStep("menu");
            }}
          >
            Back
          </Button>
        </CardFooter>
      </Card>
    );
  }

  if (step === "totp-qr") {
    return (
      <Card className="mx-auto w-full max-w-lg">
        <CardHeader>
          <CardTitle>Scan QR code</CardTitle>
          <CardDescription>Add this account in Google Authenticator, 1Password, or another TOTP app.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex justify-center rounded-lg bg-white p-4">
            <QRCodeSVG value={otpauthUri} size={200} level="M" />
          </div>
          <form onSubmit={confirmTotp} className="space-y-2">
            <Label htmlFor="enroll-totp">Enter the 6-digit code</Label>
            <Input
              id="enroll-totp"
              value={confirmCode}
              onChange={(e) => setConfirmCode(e.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
              required
            />
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Checking…" : "Confirm"}
            </Button>
          </form>
        </CardContent>
      </Card>
    );
  }

  if (step === "totp-done" && backupCodes !== null) {
    const hasCodes = backupCodes.length > 0;
    return (
      <Card className="mx-auto w-full max-w-lg">
        <CardHeader>
          <CardTitle>{hasCodes ? "Save backup codes" : "Authenticator added"}</CardTitle>
          <CardDescription>
            {hasCodes
              ? "Each code works once. Store them offline — they will not be shown again."
              : "You can use this sign-in method when signing in or before connecting to a workspace. Add another method anytime from account settings."}
          </CardDescription>
        </CardHeader>
        {hasCodes ? (
          <CardContent>
            <ul className="grid gap-1 font-mono text-sm">
              {backupCodes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </CardContent>
        ) : null}
        <CardFooter>
          {typeof onDone === "function" ? (
            <Button type="button" className="w-full" onClick={onDone}>
              Done
            </Button>
          ) : (
            <Button asChild className="w-full">
              <Link to={doneHref}>Done</Link>
            </Button>
          )}
        </CardFooter>
      </Card>
    );
  }

  if (step === "webauthn-done") {
    return (
      <Card className="mx-auto w-full max-w-lg">
        <CardHeader>
          <CardTitle>Security key registered</CardTitle>
          <CardDescription>
            You can use this key when signing in or before connecting to a workspace. Add more keys or an authenticator app if you like — only one method is required per sign-in.
          </CardDescription>
        </CardHeader>
        <CardFooter>
          {typeof onDone === "function" ? (
            <Button type="button" className="w-full" onClick={onDone}>
              Done
            </Button>
          ) : (
            <Button asChild className="w-full">
              <Link to={doneHref}>Back to dashboard</Link>
            </Button>
          )}
        </CardFooter>
      </Card>
    );
  }

  return null;
}
