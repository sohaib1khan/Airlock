import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import api from "@/utils/api";

const blankForm = {
  name: "",
  description: "",
  docker_image: "",
  tools_csv: "",
  persistent_volume: false,
  volume_path: "",
  max_runtime_minutes: "",
  workspace_home: "/home/kuser",
  env_vars_json: "{}",
  resource_limits_json: "{}",
};

function normalizePayload(form) {
  let env = {};
  let limits = {};
  try {
    env = JSON.parse(form.env_vars_json || "{}");
  } catch {
    throw new Error("env_vars must be valid JSON object");
  }
  try {
    limits = JSON.parse(form.resource_limits_json || "{}");
  } catch {
    throw new Error("resource_limits must be valid JSON object");
  }
  let maxRuntime = null;
  if (String(form.max_runtime_minutes).trim()) {
    maxRuntime = Number(form.max_runtime_minutes);
    if (!Number.isFinite(maxRuntime) || maxRuntime < 1) {
      throw new Error("auto-expire minutes must be a positive number");
    }
  }
  return {
    name: form.name.trim(),
    description: form.description.trim(),
    docker_image: form.docker_image.trim(),
    tools: form.tools_csv
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean),
    persistent_volume: Boolean(form.persistent_volume),
    volume_path: form.volume_path.trim() || null,
    max_runtime_minutes: maxRuntime,
    workspace_home: (form.workspace_home || "/home/kuser").trim() || "/home/kuser",
    env_vars: env,
    resource_limits: limits,
  };
}

export default function ContainerTemplatesAdmin() {
  const [templates, setTemplates] = useState([]);
  const [localImages, setLocalImages] = useState([]);
  const [selectedLocalImage, setSelectedLocalImage] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [form, setForm] = useState(blankForm);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [testPullImage, setTestPullImage] = useState("");
  const [importFile, setImportFile] = useState(null);
  const [overwriteImport, setOverwriteImport] = useState(false);

  const selected = useMemo(
    () => templates.find((t) => t.id === selectedId) ?? null,
    [templates, selectedId],
  );

  async function refresh() {
    const [templatesRes, localImagesRes] = await Promise.all([
      api.get("/api/containers"),
      api.get("/api/containers/actions/local-images"),
    ]);
    setTemplates(templatesRes.data);
    setLocalImages(localImagesRes.data ?? []);
  }

  useEffect(() => {
    refresh().catch(() => setMessage("Failed to load templates"));
  }, []);

  function loadIntoForm(tpl) {
    setSelectedId(tpl.id);
    setForm({
      name: tpl.name ?? "",
      description: tpl.description ?? "",
      docker_image: tpl.docker_image ?? "",
      tools_csv: (tpl.tools ?? []).join(", "),
      persistent_volume: Boolean(tpl.persistent_volume),
      volume_path: tpl.volume_path ?? "",
      max_runtime_minutes: tpl.max_runtime_minutes ?? "",
      workspace_home: tpl.workspace_home ?? "/home/kuser",
      env_vars_json: JSON.stringify(tpl.env_vars ?? {}, null, 2),
      resource_limits_json: JSON.stringify(tpl.resource_limits ?? {}, null, 2),
    });
  }

  function resetForm() {
    setSelectedId(null);
    setForm(blankForm);
  }

  async function saveTemplate(e) {
    e.preventDefault();
    setMessage("");
    let payload;
    try {
      payload = normalizePayload(form);
    } catch (err) {
      setMessage(err.message);
      return;
    }

    setBusy(true);
    try {
      if (selectedId) {
        await api.put(`/api/containers/${selectedId}`, payload);
        setMessage("Template updated");
      } else {
        await api.post("/api/containers", payload);
        setMessage("Template created");
      }
      await refresh();
      if (!selectedId) resetForm();
    } catch (err) {
      setMessage(err.response?.data?.error ?? "Failed to save template");
    } finally {
      setBusy(false);
    }
  }

  async function deleteTemplate() {
    if (!selectedId) return;
    setBusy(true);
    setMessage("");
    try {
      await api.delete(`/api/containers/${selectedId}`);
      setMessage("Template deleted");
      await refresh();
      resetForm();
    } catch (err) {
      setMessage(err.response?.data?.error ?? "Failed to delete template");
    } finally {
      setBusy(false);
    }
  }

  async function runTestPull() {
    if (!testPullImage.trim()) return;
    setBusy(true);
    setMessage("");
    try {
      await api.post("/api/containers/actions/test-pull", {
        name: "test",
        description: "",
        docker_image: testPullImage.trim(),
        tools: [],
        persistent_volume: false,
        volume_path: null,
        max_runtime_minutes: null,
        workspace_home: "/home/kuser",
        env_vars: {},
        resource_limits: {},
      });
      setMessage("Image pull test succeeded");
    } catch (err) {
      setMessage(err.response?.data?.error ?? "Image pull test failed");
    } finally {
      setBusy(false);
    }
  }

  async function exportSelectedTemplate() {
    if (!selectedId) return;
    setBusy(true);
    setMessage("");
    try {
      const { data } = await api.get(`/api/containers/${selectedId}/export.yaml`, {
        responseType: "text",
      });
      const blob = new Blob([data], { type: "application/x-yaml" });
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `${selected?.name || "template"}.airlock-template.yaml`;
      a.click();
      URL.revokeObjectURL(blobUrl);
      setMessage("Template export downloaded");
    } catch (err) {
      setMessage(err.response?.data?.error ?? "Template export failed");
    } finally {
      setBusy(false);
    }
  }

  async function importTemplateFromFile() {
    if (!importFile) return;
    setBusy(true);
    setMessage("");
    try {
      const formData = new FormData();
      formData.append("file", importFile);
      await api.post("/api/containers/actions/import-file", formData, {
        params: { overwrite_existing: overwriteImport },
        headers: { "Content-Type": "multipart/form-data" },
      });
      setMessage("Template import succeeded");
      setImportFile(null);
      await refresh();
    } catch (err) {
      const msg = err.response?.data?.error ?? err.message ?? "Template import failed";
      setMessage(typeof msg === "string" ? msg : "Template import failed");
    } finally {
      setBusy(false);
    }
  }

  function useLocalImageForTemplate() {
    if (!selectedLocalImage) return;
    setForm((f) => ({ ...f, docker_image: selectedLocalImage }));
  }

  function useLocalImageForTestPull() {
    if (!selectedLocalImage) return;
    setTestPullImage(selectedLocalImage);
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
      <Card>
        <CardHeader>
          <CardTitle>Templates</CardTitle>
          <CardDescription>Admin container template library.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Button type="button" className="w-full" variant="secondary" onClick={resetForm}>
            New template
          </Button>
          <div className="max-h-[420px] space-y-1 overflow-auto rounded border border-border p-2">
            {templates.map((tpl) => (
              <button
                key={tpl.id}
                type="button"
                className={`w-full rounded px-2 py-2 text-left text-xs ${
                  selectedId === tpl.id ? "bg-secondary text-secondary-foreground" : "hover:bg-accent"
                }`}
                onClick={() => loadIntoForm(tpl)}
              >
                <div className="flex items-center gap-1 font-medium">
                  {tpl.name}
                  {tpl.is_builtin ? (
                    <span className="rounded bg-primary/10 px-1 py-0.5 text-[10px] text-primary">
                      built-in
                    </span>
                  ) : null}
                </div>
                <div className="truncate text-muted-foreground">{tpl.docker_image}</div>
              </button>
            ))}
            {!templates.length ? (
              <p className="text-xs text-muted-foreground">No templates yet.</p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Downloaded images</CardTitle>
            <CardDescription>
              Select Docker images already available on this host and autofill template fields.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Label htmlFor="local-image-select">Local Docker image</Label>
            <select
              id="local-image-select"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={selectedLocalImage}
              onChange={(e) => setSelectedLocalImage(e.target.value)}
            >
              <option value="">Select downloaded image…</option>
              {localImages.map((img) => (
                <option key={img} value={img}>
                  {img}
                </option>
              ))}
            </select>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={useLocalImageForTemplate}
                disabled={!selectedLocalImage}
              >
                Autofill template image
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={useLocalImageForTestPull}
                disabled={!selectedLocalImage}
              >
                Autofill test pull
              </Button>
            </div>
            {!localImages.length ? (
              <p className="text-xs text-muted-foreground">
                No tagged local images found yet. Use test pull or docker build first.
              </p>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{selected ? "Edit template" : "Create template"}</CardTitle>
            <CardDescription>Define Docker image and runtime metadata.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={saveTemplate}>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Name</Label>
                  <Input
                    value={form.name}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label>Docker image</Label>
                  <Input
                    value={form.docker_image}
                    onChange={(e) => setForm((f) => ({ ...f, docker_image: e.target.value }))}
                    required
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label>File browser home</Label>
                <Input
                  placeholder="/home/kuser or /home/kasm-user (Kasm images)"
                  value={form.workspace_home}
                  onChange={(e) => setForm((f) => ({ ...f, workspace_home: e.target.value }))}
                />
                <p className="text-xs text-muted-foreground">
                  Directory the Files panel lists and uploads under. Must exist in the container image.
                </p>
              </div>
              <div className="space-y-2">
                <Label>Description</Label>
                <textarea
                  className="min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label>Tools (comma separated)</Label>
                <Input
                  value={form.tools_csv}
                  onChange={(e) => setForm((f) => ({ ...f, tools_csv: e.target.value }))}
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Persistent volume path</Label>
                  <Input
                    placeholder="/data/workspace"
                    value={form.volume_path}
                    onChange={(e) => setForm((f) => ({ ...f, volume_path: e.target.value }))}
                    disabled={!form.persistent_volume}
                  />
                </div>
                <label className="flex items-center gap-2 pt-8 text-sm">
                  <input
                    type="checkbox"
                    checked={form.persistent_volume}
                    onChange={(e) => setForm((f) => ({ ...f, persistent_volume: e.target.checked }))}
                  />
                  Enable persistence
                </label>
              </div>
              <div className="space-y-2">
                <Label>Container auto-expire (minutes)</Label>
                <Input
                  type="number"
                  min={1}
                  max={10080}
                  placeholder="Leave empty for no expiry"
                  value={form.max_runtime_minutes}
                  onChange={(e) => setForm((f) => ({ ...f, max_runtime_minutes: e.target.value }))}
                />
                <p className="text-xs text-muted-foreground">
                  Running sessions from this template are automatically stopped after this duration.
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Env vars JSON</Label>
                  <textarea
                    className="min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
                    value={form.env_vars_json}
                    onChange={(e) => setForm((f) => ({ ...f, env_vars_json: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Resource limits JSON</Label>
                  <textarea
                    className="min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
                    value={form.resource_limits_json}
                    onChange={(e) => setForm((f) => ({ ...f, resource_limits_json: e.target.value }))}
                  />
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="submit" disabled={busy}>
                  {busy ? "Saving…" : selected ? "Update template" : "Create template"}
                </Button>
                {selected ? (
                  <Button type="button" variant="outline" onClick={exportSelectedTemplate} disabled={busy}>
                    Export
                  </Button>
                ) : null}
                {selected && !selected.is_builtin ? (
                  <Button type="button" variant="destructive" onClick={deleteTemplate} disabled={busy}>
                    Delete
                  </Button>
                ) : null}
              </div>
              {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Test Docker pull</CardTitle>
            <CardDescription>Validate image availability before saving templates.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 sm:flex-row">
            <Input
              placeholder="ghcr.io/example/workspace:latest"
              value={testPullImage}
              onChange={(e) => setTestPullImage(e.target.value)}
            />
            <Button type="button" onClick={runTestPull} disabled={busy || !testPullImage.trim()}>
              Test pull
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Import / export templates</CardTitle>
            <CardDescription>
              Export selected templates to YAML and import YAML/JSON files into another deployment.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <input
              type="file"
              accept="application/x-yaml,text/yaml,.yaml,.yml,application/json,.json"
              onChange={(e) => setImportFile(e.target.files?.[0] ?? null)}
            />
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={overwriteImport}
                onChange={(e) => setOverwriteImport(e.target.checked)}
              />
              Overwrite if template name already exists
            </label>
            <Button
              type="button"
              onClick={importTemplateFromFile}
              disabled={busy || !importFile}
              variant="secondary"
            >
              Import template file (YAML/JSON)
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
