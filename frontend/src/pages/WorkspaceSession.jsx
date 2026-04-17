import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { FileExplorer } from "@/components/FileExplorer";
import { SessionFrame } from "@/components/SessionFrame";
import { Toolbar } from "@/components/Toolbar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import api from "@/utils/api";

export default function WorkspaceSessionPage() {
  const { sessionId } = useParams();
  const [session, setSession] = useState(null);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [filesOpen, setFilesOpen] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { data } = await api.get(`/api/sessions/${sessionId}`);
        if (!cancelled) setSession(data);
      } catch (err) {
        if (!cancelled) {
          setError(err.response?.data?.error ?? "Could not load session");
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return undefined;
    const id = window.setInterval(async () => {
      try {
        const { data } = await api.get(`/api/sessions/${sessionId}`);
        setSession(data);
      } catch {
        // passive polling; keep current state
      }
    }, 7000);
    return () => window.clearInterval(id);
  }, [sessionId]);

  async function doAction(action) {
    try {
      const { data } = await api.post(`/api/sessions/${sessionId}/${action}`);
      setSession(data);
      setError("");
      setStatusMessage(`Session ${action} complete`);
    } catch (err) {
      setError(err.response?.data?.error ?? `Could not ${action} session`);
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Workspace Session</CardTitle>
          <CardDescription>
            Session ID: <span className="font-mono">{sessionId}</span>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {session ? (
            <>
              <Toolbar
                sessionId={sessionId}
                status={session.status}
                onStatusMessage={(msg) => setStatusMessage(msg)}
              />
              <p className="text-sm text-foreground">
                Status: <span className="font-medium">{session.status}</span>
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => doAction("pause")}
                  disabled={session.status === "PAUSED" || session.status === "STOPPED"}
                >
                  Pause
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => doAction("resume")}
                  disabled={session.status === "RUNNING" || session.status === "STOPPED"}
                >
                  Resume
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="destructive"
                  onClick={() => doAction("stop")}
                  disabled={session.status === "STOPPED"}
                >
                  Stop
                </Button>
                <Button asChild variant="outline" size="sm">
                  <Link to="/dashboard">Back to dashboard</Link>
                </Button>
              </div>
              <div className="flex flex-col gap-4">
                <SessionFrame session={session} />
                {filesOpen ? (
                  <FileExplorer
                    sessionId={sessionId}
                    workspaceHome={session.workspace_home || "/home/kuser"}
                    onStatusMessage={(msg) => setStatusMessage(msg)}
                    onHide={() => setFilesOpen(false)}
                  />
                ) : (
                  <button
                    type="button"
                    title="Show files"
                    onClick={() => setFilesOpen(true)}
                    className="flex items-center justify-center gap-2 h-9 w-full rounded-xl border border-border bg-muted hover:bg-accent text-muted-foreground text-xs font-medium transition-colors"
                  >
                    <span>Files</span>
                    <span className="text-base leading-none">↑</span>
                  </button>
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Loading session…</p>
          )}
          {statusMessage ? <p className="text-sm text-muted-foreground">{statusMessage}</p> : null}
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </CardContent>
      </Card>
    </div>
  );
}
