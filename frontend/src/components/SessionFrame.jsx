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
  const mountRef = useRef(null);  // fullscreen wrapper
  const vncRef = useRef(null);    // noVNC canvas target
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
    if (!session?.id || !session?.websocket_url || !vncRef.current) return;
    let cancelled = false;
    let rfb = null;

    async function connect() {
      try {
        setStatus("Issuing session ticket…");
        const { data } = await api.post(`/api/sessions/${session.id}/ticket`);
        if (cancelled) return;
        const targetUrl = toAbsoluteWebSocketUrl(data.websocket_url);
        setStatus("Connecting noVNC transport…");
        rfb = new RFB(vncRef.current, targetUrl);
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
    el.value = " ";
    el.focus();
    el.setSelectionRange(1, 1);
    setStatus("Mobile keyboard ready — tap here to type");
  }

  function sendKeysym(keysym) {
    try {
      rfbRef.current?.sendKey(keysym, "", true);
      rfbRef.current?.sendKey(keysym, "", false);
    } catch {
      // ignore
    }
  }

  function onMobileKeyDown(e) {
    if (!rfbRef.current) return;
    // Intercept special keys that won't produce an input event.
    const map = {
      Backspace:  0xFF08,
      Tab:        0xFF09,
      Enter:      0xFF0D,
      Escape:     0xFF1B,
      Delete:     0xFFFF,
      ArrowLeft:  0xFF51,
      ArrowUp:    0xFF52,
      ArrowRight: 0xFF53,
      ArrowDown:  0xFF54,
      Home:       0xFF50,
      End:        0xFF57,
      PageUp:     0xFF55,
      PageDown:   0xFF56,
    };
    if (map[e.key] !== undefined) {
      e.preventDefault();
      sendKeysym(map[e.key]);
    }
  }

  function onMobileInput(e) {
    if (!rfbRef.current) return;
    const el = e.target;
    const val = el.value;
    // Sentinel char is a single space (" "). Anything after it = newly typed chars.
    // If val is empty, user hit Backspace and consumed the sentinel — send BS.
    if (val.length === 0) {
      sendKeysym(0xFF08); // Backspace
    } else if (val.length > 1) {
      // Characters typed since last reset (everything after the sentinel space).
      const newChars = val.slice(1);
      for (const ch of newChars) {
        const code = ch.codePointAt(0);
        sendKeysym(code);
      }
    }
    // Reset to sentinel so next keypress is always detectable.
    el.value = " ";
    el.setSelectionRange(1, 1);
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
      {/* Hide verbose debug info on mobile to maximise VNC space */}
      <div className={`rounded-md border border-border bg-card p-3 text-xs text-muted-foreground ${showMobileKeyboard ? "hidden sm:block" : ""}`}>
        <div>
          Proxy path: <span className="font-mono text-foreground">{session.proxy_path}</span>
        </div>
        <div>
          WebSocket: <span className="font-mono text-foreground">{session.websocket_url}</span>
        </div>
        <div>
          Status: <span className="font-medium text-foreground">{status}</span>
        </div>
      </div>
      {/* Wrapper is the fullscreen target so overlays inside remain visible */}
      <div
        ref={mountRef}
        className={`relative overflow-hidden rounded-md border border-border bg-black ${
          isFullscreen ? "h-screen w-screen" : ""
        }`}
        style={{
          touchAction: "none",
          // dvh = dynamic viewport height: shrinks automatically when the mobile
          // soft keyboard opens, so the VNC frame stays fully visible.
          // resizeSession:true on the RFB tells the remote desktop to resize to fit.
          height: isFullscreen
            ? undefined
            : showMobileKeyboard
              ? "55dvh"
              : "520px",
        }}
      >
        {/* noVNC renders into this inner div */}
        <div ref={vncRef} className="absolute inset-0" />
        {showMobileKeyboard ? (
          <button
            type="button"
            onClick={openMobileKeyboard}
            className="absolute bottom-3 left-1/2 z-10 -translate-x-1/2 rounded-full border border-white/20 bg-black/60 px-4 py-2 text-xs text-white backdrop-blur-sm active:bg-black/80"
            style={{ touchAction: "manipulation" }}
          >
            ⌨ Keyboard
          </button>
        ) : null}
        <textarea
          ref={mobileInputRef}
          rows={1}
          defaultValue=" "
          inputMode="text"
          autoCapitalize="off"
          autoCorrect="off"
          autoComplete="off"
          spellCheck={false}
          onKeyDown={onMobileKeyDown}
          onInput={onMobileInput}
          aria-label="Mobile keyboard input bridge"
          style={{
            position: "fixed",
            bottom: 0,
            left: 0,
            width: "100%",
            height: "1px",
            opacity: 0,
            pointerEvents: "none",
            zIndex: -1,
          }}
        />
      </div>
      {/* Hidden audio element — connected to the container audio stream when user enables audio */}
      <audio ref={audioRef} style={{ display: "none" }} />
    </div>
  );
}
