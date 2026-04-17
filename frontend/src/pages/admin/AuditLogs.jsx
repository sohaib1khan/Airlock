import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import api from "@/utils/api";

const PAGE_SIZE = 25;

export default function AuditLogsPage() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [eventType, setEventType] = useState("");
  const [userId, setUserId] = useState("");
  const [result, setResult] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  function resultPill(resultValue) {
    const normalized = String(resultValue || "").toUpperCase();
    if (normalized === "SUCCESS") return "bg-emerald-500/15 text-emerald-300";
    if (normalized === "FAIL") return "bg-rose-500/15 text-rose-300";
    if (normalized === "BLOCKED") return "bg-amber-500/15 text-amber-300";
    return "bg-secondary text-secondary-foreground";
  }

  async function load(nextOffset = offset) {
    setBusy(true);
    setMessage("");
    try {
      const { data } = await api.get("/api/admin/audit-logs", {
        params: {
          offset: nextOffset,
          limit: PAGE_SIZE,
          event_type: eventType || undefined,
          user_id: userId || undefined,
          result: result || undefined,
        },
      });
      setItems(Array.isArray(data.items) ? data.items : []);
      setTotal(data.total ?? 0);
      setOffset(nextOffset);
    } catch (err) {
      setMessage(err.response?.data?.error ?? "Could not load audit logs");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    load(0);
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Audit log viewer</CardTitle>
        <CardDescription>Filter security events and review activity history.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-2 sm:grid-cols-4">
          <Input
            placeholder="event_type"
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            className="text-xs"
          />
          <Input
            placeholder="user_id"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            className="font-mono text-xs"
          />
          <Input
            placeholder="result (SUCCESS/FAIL/BLOCKED)"
            value={result}
            onChange={(e) => setResult(e.target.value.toUpperCase())}
            className="text-xs"
          />
          <Button type="button" onClick={() => load(0)} disabled={busy}>
            Apply filters
          </Button>
        </div>
        <div className="space-y-2">
          {items.map((row) => (
            <div key={row.id} className="rounded border border-border p-2 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">{row.event_type}</p>
                <span className={`rounded px-2 py-0.5 text-[11px] ${resultPill(row.result)}`}>
                  {row.result}
                </span>
              </div>
              <p className="mt-1 text-muted-foreground">
                {new Date(row.timestamp).toLocaleString()} · IP {row.source_ip} · Trace {row.trace_id || "—"}
              </p>
              <p className="font-mono text-[11px] text-muted-foreground">user_id: {row.user_id || "—"}</p>
              <details className="mt-1">
                <summary className="cursor-pointer text-[11px] text-muted-foreground">
                  Technical details
                </summary>
                <p className="mt-1 font-mono text-[11px] text-muted-foreground">id: {row.id}</p>
              </details>
            </div>
          ))}
          {!items.length ? <p className="text-xs text-muted-foreground">No audit events found.</p> : null}
        </div>
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            Showing {items.length ? offset + 1 : 0}-{offset + items.length} of {total}
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy || offset === 0}
              onClick={() => load(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy || offset + PAGE_SIZE >= total}
              onClick={() => load(offset + PAGE_SIZE)}
            >
              Next
            </Button>
          </div>
        </div>
        {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
      </CardContent>
    </Card>
  );
}
