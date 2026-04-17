import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import api from "@/utils/api";

export function Toolbar({ sessionId, status, onStatusMessage }) {
  const navigate = useNavigate();
  const [audioEnabled, setAudioEnabled] = useState(true);
  const [clipboardEnabled, setClipboardEnabled] = useState(true);
  const [clipboardDraft, setClipboardDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    function onFsChange() {
      setIsFullscreen(Boolean(document.fullscreenElement));
    }
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  async function disconnectSession() {
    if (!sessionId) return;
    setBusy(true);
    try {
      await api.post(`/api/sessions/${sessionId}/stop`);
      onStatusMessage?.("Session disconnected");
      navigate("/dashboard", { replace: true });
    } catch (err) {
      const msg = err.response?.data?.error ?? "Could not disconnect session";
      onStatusMessage?.(msg);
    } finally {
      setBusy(false);
    }
  }

  async function copySessionId() {
    try {
      await navigator.clipboard.writeText(sessionId);
      onStatusMessage?.("Session ID copied");
    } catch {
      onStatusMessage?.("Clipboard access denied by browser");
    }
  }

  function toggleFullscreen() {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else {
      window.dispatchEvent(new CustomEvent("airlock-fullscreen"));
    }
  }

  async function readClipboardToDraft() {
    if (!clipboardEnabled) {
      onStatusMessage?.("Enable clipboard sync first");
      return;
    }
    try {
      const text = await navigator.clipboard.readText();
      setClipboardDraft(text || "");
      onStatusMessage?.("Clipboard loaded");
    } catch {
      onStatusMessage?.("Browser denied clipboard read");
    }
  }

  function sendClipboardToRemote() {
    if (!clipboardEnabled) {
      onStatusMessage?.("Enable clipboard sync first");
      return;
    }
    window.dispatchEvent(
      new CustomEvent("airlock-send-clipboard", { detail: { text: clipboardDraft } }),
    );
    onStatusMessage?.("Sent clipboard text to remote session");
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-card p-2">
      <Button type="button" size="sm" variant="secondary" onClick={copySessionId}>
        Copy session ID
      </Button>
      <Button
        type="button"
        size="sm"
        variant={clipboardEnabled ? "secondary" : "outline"}
        onClick={() => {
          setClipboardEnabled((v) => !v);
          window.dispatchEvent(
            new CustomEvent("airlock-clipboard-enabled", {
              detail: { enabled: !clipboardEnabled },
            }),
          );
          onStatusMessage?.(clipboardEnabled ? "Clipboard sync off" : "Clipboard sync on");
        }}
      >
        Clipboard {clipboardEnabled ? "On" : "Off"}
      </Button>
      <Button
        type="button"
        size="sm"
        variant={audioEnabled ? "secondary" : "outline"}
        onClick={() => {
          setAudioEnabled((v) => !v);
          window.dispatchEvent(
            new CustomEvent("airlock-audio-enabled", {
              detail: { enabled: !audioEnabled },
            }),
          );
          onStatusMessage?.(audioEnabled ? "Audio muted" : "Audio unmuted");
        }}
      >
        Audio {audioEnabled ? "On" : "Off"}
      </Button>
      <Button type="button" size="sm" variant={isFullscreen ? "secondary" : "outline"} onClick={toggleFullscreen}>
        {isFullscreen ? "Exit fullscreen" : "Fullscreen"}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="destructive"
        disabled={busy || status === "STOPPED"}
        onClick={disconnectSession}
      >
        {busy ? "Disconnecting…" : "Disconnect"}
      </Button>
      <input
        type="text"
        value={clipboardDraft}
        onChange={(e) => setClipboardDraft(e.target.value)}
        placeholder="Clipboard text"
        className="h-9 min-w-[180px] flex-1 rounded-md border border-input bg-background px-2 text-xs"
      />
      <Button type="button" size="sm" variant="outline" onClick={readClipboardToDraft}>
        Read clipboard
      </Button>
      <Button type="button" size="sm" variant="outline" onClick={sendClipboardToRemote}>
        Send to remote
      </Button>
    </div>
  );
}
