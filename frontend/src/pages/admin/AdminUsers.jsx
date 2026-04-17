import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/authStore";
import api from "@/utils/api";

const emptyForm = {
  username: "",
  password: "",
  is_admin: false,
  is_active: true,
};

export default function AdminUsersPage() {
  const currentUser = useAuthStore((s) => s.user);
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [revokeSessionId, setRevokeSessionId] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function refreshUsers() {
    const { data } = await api.get("/api/admin/users");
    setUsers(data);
  }

  useEffect(() => {
    refreshUsers().catch(() => setMessage("Could not load users"));
  }, []);

  async function createUser(e) {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await api.post("/api/admin/users", form);
      setMessage("User created");
      setForm(emptyForm);
      await refreshUsers();
    } catch (err) {
      setMessage(err.response?.data?.error ?? "Could not create user");
    } finally {
      setBusy(false);
    }
  }

  async function patchUser(userId, patch) {
    setBusy(true);
    setMessage("");
    try {
      await api.put(`/api/admin/users/${userId}`, patch);
      setMessage("User updated");
      await refreshUsers();
    } catch (err) {
      setMessage(err.response?.data?.error ?? "Could not update user");
    } finally {
      setBusy(false);
    }
  }

  async function deleteUser(userId, username) {
    const ok = window.confirm(`Delete user "${username}"? This cannot be undone.`);
    if (!ok) return;
    setBusy(true);
    setMessage("");
    try {
      await api.delete(`/api/admin/users/${userId}`);
      setMessage("User deleted");
      await refreshUsers();
    } catch (err) {
      const d = err.response?.data;
      const msg =
        (typeof d?.error === "string" && d.error) ||
        (typeof d?.detail === "string" && d.detail) ||
        err.message ||
        "Could not delete user";
      setMessage(msg);
    } finally {
      setBusy(false);
    }
  }

  async function revokeSession() {
    if (!revokeSessionId.trim()) return;
    const ok = window.confirm("Revoke this session now?");
    if (!ok) return;
    setBusy(true);
    setMessage("");
    try {
      await api.post(`/api/admin/sessions/${revokeSessionId.trim()}/revoke`);
      setMessage("Session revoked");
      setRevokeSessionId("");
    } catch (err) {
      setMessage(err.response?.data?.error ?? "Could not revoke session");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>User management</CardTitle>
          <CardDescription>Create users and manage account access.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={createUser}>
            <div className="space-y-2">
              <Label htmlFor="new-username">Username</Label>
              <Input
                id="new-username"
                value={form.username}
                onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-password">Temporary password</Label>
              <Input
                id="new-password"
                type="password"
                value={form.password}
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                required
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_admin}
                onChange={(e) => setForm((f) => ({ ...f, is_admin: e.target.checked }))}
              />
              Admin user
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
              />
              Active
            </label>
            <div className="sm:col-span-2">
              <Button type="submit" disabled={busy}>
                Create user
              </Button>
            </div>
          </form>
          <div className="space-y-2 rounded-md border border-border p-3">
            <p className="text-sm font-medium">Users</p>
            <div className="space-y-2">
              {users.map((u) => (
                <div
                  key={u.id}
                  className="rounded border border-border p-2 text-xs"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="font-medium">{u.username}</p>
                      <p className="text-muted-foreground">
                        {u.is_admin ? "Admin" : "User"} · {u.is_active ? "Active" : "Disabled"} ·{" "}
                        {u.force_password_reset ? "Password reset required" : "Password OK"} ·{" "}
                        {u.mfa_enrolled ? "2FA on" : "2FA not enrolled"}
                      </p>
                    </div>
                    <p className="font-mono text-[11px] text-muted-foreground">{u.id}</p>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      type="button"
                      disabled={busy || u.id === currentUser?.id}
                      onClick={() => patchUser(u.id, { is_active: !u.is_active })}
                    >
                      {u.is_active ? "Disable" : "Enable"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      type="button"
                      disabled={busy}
                      onClick={() => patchUser(u.id, { force_password_reset: true })}
                    >
                      Force reset
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      type="button"
                      disabled={busy || u.id === currentUser?.id}
                      onClick={() => deleteUser(u.id, u.username)}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              ))}
              {!users.length ? <p className="text-xs text-muted-foreground">No users found.</p> : null}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Session revocation</CardTitle>
          <CardDescription>Revoke any workspace session by ID.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 sm:flex-row">
          <Input
            value={revokeSessionId}
            onChange={(e) => setRevokeSessionId(e.target.value)}
            placeholder="session uuid"
            className="font-mono text-xs"
          />
          <Button type="button" variant="destructive" onClick={revokeSession} disabled={busy}>
            Revoke session
          </Button>
        </CardContent>
      </Card>
      {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
    </div>
  );
}
