import { Link } from "react-router-dom";
import { useState } from "react";
import { Shield } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import api from "@/utils/api";

export default function AdminSettingsPage() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function changePassword(e) {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await api.post("/api/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setMessage("Password changed successfully.");
    } catch (err) {
      setMessage(err.response?.data?.error ?? "Could not change password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Admin settings</CardTitle>
          <CardDescription>Manage security settings and workspace configuration.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="overflow-hidden rounded-lg border border-border bg-gradient-to-br from-muted/50 to-muted/20">
            <div className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
              <div className="flex gap-3 sm:items-start">
                <div
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary"
                  aria-hidden
                >
                  <Shield className="h-5 w-5" strokeWidth={1.75} />
                </div>
                <div className="min-w-0 space-y-1">
                  <p className="text-sm font-semibold leading-tight">Two-factor authentication</p>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    Add or remove authenticator apps, security keys, and backup codes. Your account must keep at least
                    one active method.
                  </p>
                </div>
              </div>
              <Button asChild className="w-full shrink-0 sm:w-auto">
                <Link to="/account/2fa">Manage 2FA</Link>
              </Button>
            </div>
          </div>

          <div className="rounded-md border border-border p-4">
            <p className="text-sm font-medium">Administration</p>
            <p className="mt-1 text-xs text-muted-foreground">Users, audit trail, and related tools.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button variant="outline" asChild>
                <Link to="/admin/users">User management</Link>
              </Button>
              <Button variant="outline" asChild>
                <Link to="/admin/audit-logs">Audit logs</Link>
              </Button>
            </div>
          </div>

          <div className="rounded-md border border-border p-4">
            <p className="text-sm font-medium">Password</p>
            <p className="mt-1 text-xs text-muted-foreground">Change the password for this admin account.</p>
            <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={changePassword}>
              <div className="space-y-2">
                <Label htmlFor="pw-current">Current password</Label>
                <Input
                  id="pw-current"
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="pw-new">New password</Label>
                <Input
                  id="pw-new"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                />
              </div>
              <div className="sm:col-span-2">
                <Button type="submit" disabled={busy}>
                  Change password
                </Button>
              </div>
            </form>
            {message ? <p className="mt-2 text-xs text-muted-foreground">{message}</p> : null}
          </div>
          <div className="rounded-md border border-border p-4">
            <p className="text-sm font-medium">Workspace templates</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Manage container templates and image pull checks.
            </p>
            <div className="mt-3">
              <Button variant="outline" asChild>
                <Link to="/admin/containers">Open container templates</Link>
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
