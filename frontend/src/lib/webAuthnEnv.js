import { browserSupportsWebAuthn } from "@simplewebauthn/browser";

/**
 * Whether WebAuthn (security keys / passkeys) can run in this environment.
 * Fails on plain HTTP to non-localhost hosts (browsers hide PublicKeyCredential).
 */
export function isWebAuthnAvailable() {
  if (typeof globalThis === "undefined") return false;
  return browserSupportsWebAuthn();
}

/**
 * User-facing explanation when security keys cannot be used, or null if OK.
 */
export function webAuthnUnavailableExplanation() {
  if (isWebAuthnAvailable()) return null;
  const insecure = typeof window !== "undefined" && !window.isSecureContext;
  if (insecure) {
    return "Security keys and WebAuthn only work in a trusted context: use HTTPS, or open the app at http://localhost. Plain HTTP to an IP or hostname (for example http://192.168.x.x) blocks WebAuthn in browsers. Use an authenticator app (TOTP), or YubiKey 44-character OTP if your server enables it.";
  }
  return "This browser or profile does not support WebAuthn. Try Chrome, Firefox, or Edge; disable strict extensions; or use an authenticator app instead.";
}
