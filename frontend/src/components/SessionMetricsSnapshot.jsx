import { Activity } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import api from "@/utils/api";

/** Human-readable duration from milliseconds (compact). */
function formatDuration(ms) {
  if (ms < 0 || Number.isNaN(ms)) return "0s";
  const sec = Math.floor(ms / 1000);
  const min = Math.floor(sec / 60);
  const hr = Math.floor(min / 60);
  const day = Math.floor(hr / 24);
  if (day > 0) return `${day}d ${hr % 24}h`;
  if (hr > 0) return `${hr}h ${min % 60}m`;
  if (min > 0) return `${min}m ${sec % 60}s`;
  return `${sec}s`;
}

/** Parse RFC3339 / ISO; naive datetimes without offset are treated as UTC (matches Airlock API). */
function parseTime(iso) {
  if (!iso || typeof iso !== "string") return null;
  let s = iso.trim();
  if (/^\d{4}-\d{2}-\d{2}T/.test(s) && !/[zZ]$/.test(s) && !/[+-]\d{2}:?\d{2}$/.test(s)) {
    s = `${s}Z`;
  }
  const t = Date.parse(s);
  return Number.isNaN(t) ? null : t;
}

function formatBytes(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = Number(n);
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v < 10 && i > 0 ? v.toFixed(1) : Math.round(v)} ${u[i]}`;
}

function formatApiError(err) {
  const d = err.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d
      .map((x) => (typeof x?.msg === "string" ? x.msg : ""))
      .filter(Boolean)
      .join(" ");
  }
  const e = err.response?.data?.error;
  if (typeof e === "string") return e;
  return err.message ?? "Could not load metrics";
}

/**
 * Live Docker CPU/memory snapshot for a workspace session (requires running container).
 * @param {string} [startedAt] RFC3339 UTC instant — used for uptime / remaining math
 * @param {string | null} [expiresAt] RFC3339 UTC instant for scheduled stop, if any
 * @param {string} [startedAtLocal] Server-formatted start time (AIRLOCK_TIMEZONE)
 * @param {string | null} [expiresAtLocal] Server-formatted expiry time
 * @param {string} [serverTimezone] IANA zone name from API (e.g. America/New_York)
 */
export function SessionMetricsSnapshot({
  sessionId,
  onClose,
  startedAt,
  expiresAt,
  startedAtLocal,
  expiresAtLocal,
  serverTimezone,
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data: d } = await api.get(`/api/sessions/${sessionId}/metrics`);
      setData(d);
    } catch (err) {
      setError(formatApiError(err));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    load();
  }, [load]);

  const cpu = data?.available ? Number(data.cpu_percent ?? 0) : 0;
  const memPct = data?.available && data.memory_percent != null ? Number(data.memory_percent) : null;

  const startMs = parseTime(startedAt);
  const expiryMs = expiresAt ? parseTime(expiresAt) : null;
  const uptimeMs = startMs != null ? now - startMs : null;
  const remainingMs = expiryMs != null ? expiryMs - now : null;

  const startedLabel =
    (typeof startedAtLocal === "string" && startedAtLocal.trim()) ||
    (startMs != null ? new Date(startMs).toLocaleString() : "");
  const expiresLabel =
    (typeof expiresAtLocal === "string" && expiresAtLocal.trim()) ||
    (expiryMs != null ? new Date(expiryMs).toLocaleString() : "");
  const tzCaption =
    typeof serverTimezone === "string" && serverTimezone.trim()
      ? `Clock: ${serverTimezone.trim()}`
      : null;

  const scheduleBlock = (
    <div className="space-y-1.5 rounded-md border border-border/60 bg-background/40 px-2.5 py-2">
      <p className="text-[11px] font-medium text-foreground">Session schedule</p>
      {tzCaption ? (
        <p className="text-[10px] text-muted-foreground/90">{tzCaption}</p>
      ) : null}
      {uptimeMs != null ? (
        <p className="text-[11px] text-muted-foreground">
          Uptime: <span className="font-mono text-foreground">{formatDuration(uptimeMs)}</span>
          {startedLabel ? (
            <span className="block text-[10px] opacity-80">Started {startedLabel}</span>
          ) : null}
        </p>
      ) : (
        <p className="text-[11px] text-muted-foreground">Uptime: —</p>
      )}
      {expiryMs != null ? (
        remainingMs != null && remainingMs > 0 ? (
          <p className="text-[11px] text-muted-foreground">
            Time until cutoff:{" "}
            <span className="font-mono text-amber-200/95">{formatDuration(remainingMs)}</span>
            <span className="block text-[10px] opacity-80">Stops by {expiresLabel}</span>
          </p>
        ) : (
          <p className="text-[11px] text-amber-200/90">
            Past scheduled end time — the session may stop at any moment. Stop it manually if needed.
          </p>
        )
      ) : (
        <p className="text-[11px] text-muted-foreground">
          No time-based cutoff — this session is not scheduled to stop automatically (template has no max runtime or
          expiry not set).
        </p>
      )}
    </div>
  );

  return (
    <div className="rounded-md border border-border bg-muted/25 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/70 pb-2">
        <div className="flex items-center gap-2 text-xs font-medium text-foreground">
          <Activity className="h-4 w-4 text-primary" aria-hidden />
          Resource metrics
        </div>
        <div className="flex flex-wrap gap-1">
          <Button type="button" size="sm" variant="ghost" className="h-7 text-[11px]" disabled={loading} onClick={load}>
            {loading ? "Refreshing…" : "Refresh"}
          </Button>
          <Button type="button" size="sm" variant="ghost" className="h-7 text-[11px]" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>

      {loading && !data ? (
        <p className="mt-3 text-xs text-muted-foreground">Loading snapshot…</p>
      ) : (
        <div className="mt-3 space-y-3">
          {error ? (
            <p className="text-xs text-destructive">{error}</p>
          ) : data && !data.available ? (
            <p className="text-xs text-muted-foreground">{data.message}</p>
          ) : data?.available ? (
            <>
              <div>
                <div className="mb-1 flex justify-between gap-2 text-[11px] text-muted-foreground">
                  <span>CPU</span>
                  <span className="shrink-0 font-mono text-foreground">{cpu.toFixed(1)}%</span>
                </div>
                <p className="mb-1 text-[10px] leading-tight text-muted-foreground/90">
                  Share of host CPUs (can exceed 100% on multi-core).
                </p>
                <div className="h-2 overflow-hidden rounded-full bg-secondary">
                  <div
                    className={cn("h-full rounded-full bg-primary/90")}
                    style={{ width: `${Math.min(100, cpu)}%` }}
                  />
                </div>
              </div>
              <div>
                <div className="mb-1 flex justify-between gap-2 text-[11px] text-muted-foreground">
                  <span>Memory</span>
                  <span className="shrink-0 text-right font-mono text-[10px] text-foreground sm:text-[11px]">
                    {formatBytes(data.memory_usage_bytes)} / {formatBytes(data.memory_limit_bytes)}
                    {memPct != null ? ` (${memPct.toFixed(1)}%)` : ""}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full rounded-full bg-emerald-500/85"
                    style={{ width: `${Math.min(100, memPct ?? 0)}%` }}
                  />
                </div>
              </div>
              {data.container_status ? (
                <p className="text-[11px] text-muted-foreground">
                  Docker status:{" "}
                  <span className="font-mono text-foreground">{String(data.container_status)}</span>
                </p>
              ) : null}
            </>
          ) : null}
          {!loading ? scheduleBlock : null}
        </div>
      )}
    </div>
  );
}

export function sessionMetricsAvailable(status, containerId) {
  const st = String(status || "").toUpperCase();
  return Boolean(containerId && st !== "STOPPED" && st !== "ERROR");
}
