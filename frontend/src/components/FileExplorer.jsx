import { useEffect, useRef, useState } from "react";
import { ArrowUp, Download, Folder, File, RefreshCw, Upload, PanelBottomClose } from "lucide-react";

import api from "@/utils/api";

function formatBytes(bytes) {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function posixDirname(p) {
  const n = p.replace(/\/+/g, "/").replace(/\/$/, "") || "/";
  if (n === "/") return "/";
  const i = n.lastIndexOf("/");
  return i <= 0 ? "/" : n.slice(0, i);
}

export function FileExplorer({ sessionId, workspaceHome = "/home/kuser", onStatusMessage, onHide }) {
  const root = (workspaceHome || "/home/kuser").replace(/\/+$/, "") || "/home/kuser";
  const [cwd, setCwd] = useState(root);
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef(null);

  async function refreshFiles(path = cwd) {
    if (!sessionId) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/api/sessions/${sessionId}/files`, {
        params: { path },
      });
      setCwd(data.cwd || root);
      setItems(Array.isArray(data.items) ? data.items : []);
    } catch (err) {
      const msg = err.response?.data?.error ?? "Could not load files";
      onStatusMessage?.(msg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!sessionId) return;
    setCwd(root);
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const { data } = await api.get(`/api/sessions/${sessionId}/files`, {
          params: { path: root },
        });
        if (cancelled) return;
        setCwd(data.cwd || root);
        setItems(Array.isArray(data.items) ? data.items : []);
      } catch (err) {
        if (!cancelled) {
          const msg = err.response?.data?.error ?? "Could not load files";
          onStatusMessage?.(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, root]);

  // Keep the list in sync with files created from inside the desktop session.
  useEffect(() => {
    if (!sessionId) return undefined;
    const id = window.setInterval(() => {
      refreshFiles();
    }, 5000);
    return () => window.clearInterval(id);
  }, [sessionId, cwd]);

  async function onUploadChange(e) {
    const file = e.target.files?.[0];
    if (!file || !sessionId) return;
    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    try {
      await api.post(`/api/sessions/${sessionId}/upload`, form, {
        params: { destination: cwd },
        headers: { "Content-Type": "multipart/form-data" },
      });
      onStatusMessage?.(`Uploaded: ${file.name}`);
      await refreshFiles();
    } catch (err) {
      const msg = err.response?.data?.error ?? "Upload failed";
      onStatusMessage?.(msg);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  async function downloadItem(name) {
    if (!sessionId) return;
    try {
      const { data } = await api.get(`/api/sessions/${sessionId}/download`, {
        params: { path: `${cwd}/${name}` },
        responseType: "blob",
      });
      const blobUrl = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = name;
      a.click();
      URL.revokeObjectURL(blobUrl);
      onStatusMessage?.(`Download started: ${name}`);
    } catch (err) {
      const msg = err.response?.data?.error ?? "Download failed";
      onStatusMessage?.(msg);
    }
  }

  async function openDirectory(name) {
    const next = `${cwd}/${name}`.replace(/\/+/g, "/");
    await refreshFiles(next);
  }

  async function goUp() {
    if (cwd === root) return;
    const parent = posixDirname(cwd);
    if (parent.length < root.length || !parent.startsWith(root)) {
      await refreshFiles(root);
    } else {
      await refreshFiles(parent);
    }
  }

  const canGoUp = cwd !== root;

  const pathLabel = cwd.startsWith(root) ? cwd.replace(root, "~") || "~" : cwd;

  return (
    <div className="flex flex-col rounded-xl border border-border bg-card overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border px-3 py-2 bg-muted/30">
        <span className="text-xs font-semibold text-foreground flex-1 min-w-0">
          Files
          <span className="ml-2 font-mono font-normal text-muted-foreground truncate">{pathLabel}</span>
        </span>
        <button
          onClick={goUp}
          disabled={!canGoUp}
          className="p-1.5 rounded-md text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          title="Go up"
        >
          <ArrowUp size={15} />
        </button>
        <button
          onClick={() => refreshFiles(cwd)}
          className={`p-1.5 rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors ${loading ? "animate-spin" : ""}`}
          title="Refresh"
        >
          <RefreshCw size={15} />
        </button>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={busy}
          className="p-1.5 rounded-md text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50 transition-colors"
          title={busy ? "Uploading…" : "Upload file"}
        >
          <Upload size={15} />
        </button>
        {onHide ? (
          <button
            onClick={onHide}
            className="p-1.5 rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            title="Hide files"
          >
            <PanelBottomClose size={15} />
          </button>
        ) : null}
        <input ref={fileInputRef} type="file" className="hidden" onChange={onUploadChange} />
      </div>

      {/* File list */}
      <div className="divide-y divide-border/60">
        {items.length === 0 && !loading ? (
          <p className="px-4 py-6 text-center text-xs text-muted-foreground">Empty folder</p>
        ) : null}
        {loading && items.length === 0 ? (
          <p className="px-4 py-6 text-center text-xs text-muted-foreground">Loading…</p>
        ) : null}
        {items.map((item) =>
          item.type === "directory" ? (
            <button
              key={item.name}
              type="button"
              onClick={() => openDirectory(item.name)}
              className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-accent/50 active:bg-accent transition-colors"
            >
              <Folder size={16} className="shrink-0 text-blue-400" />
              <span className="min-w-0 flex-1 truncate text-sm font-medium">{item.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground">›</span>
            </button>
          ) : (
            <button
              key={item.name}
              type="button"
              onClick={() => downloadItem(item.name)}
              className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-accent/50 active:bg-accent transition-colors group"
            >
              <File size={16} className="shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate text-sm">{item.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground">
                {formatBytes(item.size)}
              </span>
              <Download
                size={14}
                className="shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity"
              />
            </button>
          )
        )}
      </div>
    </div>
  );
}
