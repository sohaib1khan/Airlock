import { useEffect, useRef, useState } from "react";
import RFB from "@novnc/novnc/core/rfb";

import api from "@/utils/api";

function toAbsoluteWebSocketUrl(relativeUrl) {
  const base = new URL(window.location.origin);
  base.protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new URL(relativeUrl, base);
  return ws.toString();
}

export function SessionFrame({ session }) {
  const mountRef = useRef(null);
  const rfbRef = useRef(null);
  const audioRef = useRef(null);
  const mobileInputRef = useRef(null);
  const sessionIdRef = useRef(session?.id ?? null);
  const [status, setStatus] = useState("Preparing transport…");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showMobileKeyboard, setShowMobileKeyboard] = useState(false);
  const clipboardEnabledRef = useRef(true);
  const audioEnabledRef = useRef(false);

  // Keep sessionIdRef in sync so event handlers can access the current session id.
  useEffect(() => {
    sessionIdRef.current = session?.id ?? null;
    // Stop any playing audio when session changes.
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
    }
    audioEnabledRef.current = false;
  }, [session?.id]);

  useEffect(() => {
    const coarsePointer =
      typeof window !== "undefined" &&
      (window.matchMedia?.("(pointer: coarse)")?.matches || "ontouchstart" in window);
    setShowMobileKeyboard(Boolean(coarsePointer));
  }, []);

  useEffect(() => {
    if (!session?.id || !session?.websocket_url || !mountRef.current) return;
    let cancelled = false;
    let rfb = null;

    async function connect() {
      try {
        setStatus("Issuing session ticket…");
        const { data } = await api.post(`/api/sessions/${session.id}/ticket`);
        if (cancelled) return;
        const targetUrl = toAbsoluteWebSocketUrl(data.websocket_url);
        setStatus("Connecting noVNC transport…");
        rfb = new RFB(mountRef.current, targetUrl);
        rfb.viewOnly = false;
        rfb.scaleViewport = true;
        rfb.resizeSession = true;
        rfb.focusOnClick = true;
        rfb.background = "#0b1220";
        rfb.addEventListener("connect", () => setStatus("Connected"));
        rfb.addEventListener("disconnect", () => setStatus("Disconnected"));
        rfb.addEventListener("securityfailure", () => setStatus("Security failure"));
        rfbRef.current = rfb;
      } catch (err) {
        if (!cancelled) {
          const msg = err.response?.data?.error ?? err.message ?? "Transport setup failed";
          setStatus(typeof msg === "string" ? msg : "Transport setup failed");
        }
      }
    }

    connect();
    return () => {
      cancelled = true;
      if (rfbRef.current) {
        try {
          rfbRef.current.disconnect();
        } catch {
          // ignore disconnect errors during unmount
        }
        rfbRef.current = null;
      }
    };
  }, [session?.id, session?.websocket_url]);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    function onPointerDown() {
      rfbRef.current?.focus();
    }
    mount.addEventListener("pointerdown", onPointerDown, { passive: true });
    return () => {
      mount.removeEventListener("pointerdown", onPointerDown);
    };
  }, []);

  function openMobileKeyboard() {
    const el = mobileInputRef.current;
    if (!el) return;
    el.focus();
    setStatus("Mobile keyboard ready");
  }

  function onMobileInputChange(event) {
    const text = event.target.value;
    if (!text) return;
    if (rfbRef.current) {
      try {
        // Mobile OS keyboards cannot target the canvas directly, so forward text via VNC clipboard.
        rfbRef.current.clipboardPasteFrom(text);
        setStatus(`Typed ${text.length} char${text.length === 1 ? "" : "s"}`);
      } catch {
        setStatus("Failed to send typed text");
      }
    }
    event.target.value = "";
  }

  useEffect(() => {
    function onClipboardToggle(event) {
      clipboardEnabledRef.current = Boolean(event.detail?.enabled);
    }
    function onAudioToggle(event) {
      const enabled = Boolean(event.detail?.enabled);
      audioEnabledRef.current = enabled;
      if (!audioRef.current || !sessionIdRef.current) return;
      if (enabled) {
        audioRef.current.src = `/api/sessions/${sessionIdRef.current}/audio`;
        audioRef.current.muted = false;
        audioRef.current.play().catch(() => {});
      } else {
        audioRef.current.pause();
        audioRef.current.src = "";
      }
    }
    function onSendClipboard(event) {
      const text = event.detail?.text;
      if (!rfbRef.current || !clipboardEnabledRef.current) return;
      if (typeof text === "string" && text.length > 0) {
        try {
          rfbRef.current.clipboardPasteFrom(text);
          setStatus("Clipboard text sent");
        } catch {
          setStatus("Clipboard send failed");
        }
      }
    }
    window.addEventListener("airlock-clipboard-enabled", onClipboardToggle);
    window.addEventListener("airlock-audio-enabled", onAudioToggle);
    window.addEventListener("airlock-send-clipboard", onSendClipboard);

    function onFullscreenRequest() {
      if (!mountRef.current) return;
      if (document.fullscreenElement) {
        document.exitFullscreen().catch(() => {});
      } else {
        mountRef.current.requestFullscreen().catch(() => {});
      }
    }
    function onFsChange() {
      setIsFullscreen(document.fullscreenElement === mountRef.current);
    }
    window.addEventListener("airlock-fullscreen", onFullscreenRequest);
    document.addEventListener("fullscreenchange", onFsChange);

    return () => {
      window.removeEventListener("airlock-clipboard-enabled", onClipboardToggle);
      window.removeEventListener("airlock-audio-enabled", onAudioToggle);
      window.removeEventListener("airlock-send-clipboard", onSendClipboard);
      window.removeEventListener("airlock-fullscreen", onFullscreenRequest);
      document.removeEventListener("fullscreenchange", onFsChange);
    };
  }, []);

  if (!session) return null;

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-border bg-card p-3 text-xs text-muted-foreground">
        <div>
          Proxy path: <span className="font-mono text-foreground">{session.proxy_path}</span>
        </div>
        <div>
          WebSocket: <span className="font-mono text-foreground">{session.websocket_url}</span>
        </div>
        <div>
          Status: <span className="font-medium text-foreground">{status}</span>
        </div>
        {showMobileKeyboard ? (
          <div className="mt-2">
            <button
              type="button"
              onClick={openMobileKeyboard}
              className="rounded-md border border-border bg-secondary px-2 py-1 text-xs text-secondary-foreground"
            >
              Open mobile keyboard
            </button>
            <input
              ref={mobileInputRef}
              type="text"
              inputMode="text"
              autoCapitalize="off"
              autoCorrect="off"
              autoComplete="off"
              spellCheck={false}
              onChange={onMobileInputChange}
              className="sr-only"
              aria-label="Mobile keyboard input bridge"
            />
          </div>
        ) : null}
      </div>
      <div
        ref={mountRef}
        className={`overflow-hidden rounded-md border border-border bg-black ${
          isFullscreen ? "h-screen w-screen" : "h-[520px]"
        }`}
        style={{ touchAction: "none" }}
      />
      {/* Hidden audio element — connected to the container audio stream when user enables audio */}
      <audio ref={audioRef} style={{ display: "none" }} />
    </div>
  );
}
