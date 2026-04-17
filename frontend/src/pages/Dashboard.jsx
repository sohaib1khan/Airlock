import { Activity } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ConnectChallenge } from "@/components/ConnectChallenge";
import { SessionMetricsSnapshot, sessionMetricsAvailable } from "@/components/SessionMetricsSnapshot";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/authStore";
import api from "@/utils/api";

export default function Dashboard() {
  const user = useAuthStore((s) => s.user);
  const [layer2Open, setLayer2Open] = useState(false);
  const [templateId, setTemplateId] = useState("");
  const [templateName, setTemplateName] = useState("");
  const [templates, setTemplates] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [sessionMessage, setSessionMessage] = useState("");
  const [metricsSessionId, setMetricsSessionId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [templatesRes, sessionsRes] = await Promise.all([
          api.get("/api/containers"),
          api.get("/api/sessions"),
        ]);
        if (!cancelled) {
          setTemplates(templatesRes.data);
          setSessions(sessionsRes.data);
        }
      } catch {
        if (!cancelled) {
          setSessionMessage("Could not load templates or sessions right now. Try refreshing in a moment.");
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleConnectVerified(connectToken, launchMode = "resume_existing", containerPassword) {
    try {
      const { data } = await api.post("/api/sessions/start", {
        template_id: templateId.trim(),
        connect_token: connectToken,
        launch_mode: launchMode,
        ...(containerPassword ? { container_password: containerPassword } : {}),
      });
      setSessions((prev) => {
        const withoutExisting = prev.filter((s) => s.id !== data.id);
        return [data, ...withoutExisting];
      });
      setSessionMessage("Workspace session started.");
    } catch (err) {
      const msg = err.response?.data?.error ?? err.message ?? "Could not start session";
      setSessionMessage(typeof msg === "string" ? msg : "Could not start session");
    }
  }

  function launchTemplate(tpl) {
    setTemplateId(tpl.id);
    setTemplateName(tpl.name);
    setLayer2Open(true);
  }

  async function applySessionAction(sessionId, action) {
    try {
      await api.post(`/api/sessions/${sessionId}/${action}`);
      const { data } = await api.get("/api/sessions");
      setSessions(data);
      setSessionMessage(`Session ${action} completed.`);
    } catch (err) {
      const msg = err.response?.data?.error ?? err.message ?? `Could not ${action} session`;
      setSessionMessage(typeof msg === "string" ? msg : `Could not ${action} session`);
    }
  }

  async function deleteSessionHistory(sessionId) {
    try {
      await api.delete(`/api/sessions/${sessionId}`);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      setMetricsSessionId((mid) => (mid === sessionId ? null : mid));
      setSessionMessage(`Session removed: ${sessionId}`);
    } catch (err) {
      const msg = err.response?.data?.error ?? err.message ?? "Could not remove session";
      setSessionMessage(typeof msg === "string" ? msg : "Could not remove session");
    }
  }

  async function cleanupOldSessions() {
    try {
      const { data } = await api.post("/api/sessions/actions/cleanup");
      const deleted = Number(data?.deleted ?? 0);
      if (deleted > 0) {
        setSessions((prev) =>
          prev.filter((s) => !["STOPPED", "ERROR"].includes(String(s.status || "").toUpperCase())),
        );
      }
      setSessionMessage(deleted ? `Cleaned ${deleted} old session(s)` : "No old sessions to clean");
    } catch (err) {
      const msg = err.response?.data?.error ?? err.message ?? "Could not clean old sessions";
      setSessionMessage(typeof msg === "string" ? msg : "Could not clean old sessions");
    }
  }

  function displayStatus(status) {
    const normalized = String(status || "").toUpperCase();
    if (normalized === "RUNNING") return "Running";
    if (normalized === "PAUSED") return "Paused";
    if (normalized === "STOPPED") return "Stopped";
    return normalized || "Unknown";
  }

  function statusClasses(status) {
    const normalized = String(status || "").toUpperCase();
    if (normalized === "RUNNING") return "bg-emerald-500/15 text-emerald-300";
    if (normalized === "PAUSED") return "bg-amber-500/15 text-amber-300";
    if (normalized === "STOPPED") return "bg-rose-500/15 text-rose-300";
    return "bg-secondary text-secondary-foreground";
  }

  function findTemplateName(templateId) {
    return templates.find((tpl) => tpl.id === templateId)?.name ?? "Template";
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Dashboard</CardTitle>
              <CardDescription>
                Launch workspaces and manage your active sessions.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-foreground">
            Signed in as{" "}
            <span className="font-medium text-primary">{user?.username ?? "—"}</span>
            {user?.is_admin ? (
              <span className="ml-2 rounded-md bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">
                Admin
              </span>
            ) : null}
          </p>
          <p className="text-xs text-muted-foreground">
            Session scope: <span className="text-foreground">{user?.scope ?? "—"}</span>
            {user?.mfa_enrolled ? " · 2FA enrolled" : ""}
            {user?.scope === "full" ? (
              <>
                {" · "}
                <Link to="/account/2fa" className="text-primary underline-offset-4 hover:underline">
                  Manage 2FA
                </Link>
              </>
            ) : null}
          </p>
          {user?.force_password_reset ? (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200">
              Password reset is required for this account.
              <Link to="/account/security" className="ml-2 underline">
                Update password now
              </Link>
            </div>
          ) : null}
          <div className="rounded-md border border-border p-4">
            <p className="mb-2 text-sm font-medium">Available templates</p>
            {templates.length ? (
              <ul className="space-y-2 text-xs">
                {templates.map((tpl) => (
                  <li key={tpl.id} className="rounded border border-border p-2">
                    <div className="text-sm font-medium">{tpl.name}</div>
                    <div className="font-mono text-[11px] text-muted-foreground">{tpl.id}</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Button type="button" size="sm" onClick={() => launchTemplate(tpl)}>
                        Connect
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">
                No templates available yet. Ask an admin to add one in Admin containers.
              </p>
            )}
            <div className="mt-4 border-t border-border pt-3">
              <p className="mb-2 text-xs text-muted-foreground">
                Manual launch (paste a template ID if needed)
              </p>
              <div className="space-y-2">
                <Label htmlFor="tpl-id">Template ID</Label>
                <Input
                  id="tpl-id"
                  value={templateId}
                  onChange={(e) => setTemplateId(e.target.value)}
                  placeholder="uuid"
                  className="font-mono text-xs"
                />
              </div>
              <Button
                type="button"
                variant="secondary"
                className="mt-3 w-full sm:w-auto"
                disabled={!templateId.trim()}
                onClick={() => {
                  setTemplateName("");
                  setLayer2Open(true);
                }}
              >
                Continue to connect challenge
              </Button>
            </div>
          </div>
          <div className="rounded-md border border-border p-4">
            <div className="mb-3 flex flex-col gap-3 sm:mb-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0 space-y-0.5">
                <p className="text-sm font-medium">My sessions</p>
                <p className="text-[11px] text-muted-foreground">
                  Control workspaces and open live Docker CPU/memory metrics when a container is running.
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="shrink-0 self-start sm:self-center"
                onClick={cleanupOldSessions}
              >
                Clean old sessions
              </Button>
            </div>
            {sessions.length ? (
              <ul className="space-y-3 text-xs">
                {sessions.map((s) => (
                  <li key={s.id} className="rounded-lg border border-border p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-foreground">
                          {findTemplateName(s.template_id)}
                        </p>
                        <p className="text-[11px] text-muted-foreground">Workspace session</p>
                      </div>
                      <span className={`shrink-0 rounded-md px-2 py-1 text-[11px] font-medium ${statusClasses(s.status)}`}>
                        {displayStatus(s.status)}
                      </span>
                    </div>
                    <div className="mt-3 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={() => applySessionAction(s.id, "pause")}
                          disabled={s.status === "PAUSED" || s.status === "STOPPED"}
                        >
                          Pause
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={() => applySessionAction(s.id, "resume")}
                          disabled={s.status === "RUNNING" || s.status === "STOPPED"}
                        >
                          Resume
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="destructive"
                          onClick={() => applySessionAction(s.id, "stop")}
                          disabled={s.status === "STOPPED"}
                        >
                          Stop
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="gap-1"
                          disabled={!sessionMetricsAvailable(s.status, s.container_id)}
                          title={
                            sessionMetricsAvailable(s.status, s.container_id)
                              ? "CPU and memory snapshot from Docker"
                              : "Metrics require an active container"
                          }
                          onClick={() =>
                            setMetricsSessionId((id) => (id === s.id ? null : s.id))
                          }
                        >
                          <Activity className="h-3.5 w-3.5" aria-hidden />
                          Metrics
                        </Button>
                        <Button type="button" size="sm" variant="outline" asChild>
                          <Link to={`/session/${s.id}`}>Open</Link>
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={() => deleteSessionHistory(s.id)}
                          disabled={!["STOPPED", "ERROR"].includes(String(s.status || "").toUpperCase())}
                        >
                          Clear
                        </Button>
                      </div>
                      {metricsSessionId === s.id ? (
                        <SessionMetricsSnapshot
                          sessionId={s.id}
                          startedAt={s.started_at}
                          expiresAt={s.expires_at}
                          startedAtLocal={s.started_at_local}
                          expiresAtLocal={s.expires_at_local}
                          serverTimezone={s.server_timezone}
                          onClose={() => setMetricsSessionId(null)}
                        />
                      ) : null}
                    </div>
                    <details className="mt-2">
                      <summary className="cursor-pointer text-[11px] text-muted-foreground">
                        Technical details
                      </summary>
                      <div className="mt-1 space-y-1 font-mono text-[11px] text-muted-foreground">
                        <p>Session ID: {s.id}</p>
                        <p>Template ID: {s.template_id}</p>
                        {s.container_id ? <p>Container: {s.container_id}</p> : null}
                      </div>
                    </details>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">No sessions running.</p>
            )}
            {sessionMessage ? <p className="mt-2 text-xs text-muted-foreground">{sessionMessage}</p> : null}
          </div>
        </CardContent>
      </Card>
      <ConnectChallenge
        open={layer2Open}
        templateId={templateId.trim()}
        templateName={templateName}
        onClose={() => setLayer2Open(false)}
        onVerified={handleConnectVerified}
      />
    </div>
  );
}
