# Bastion templates

Drop-in workspace images and Airlock template exports for **graphical bastion** sessions.

## Desktop GUI (XFCE)

Folder: `desktop-xfce/`

Airlock expects each workspace container to:

- Listen on **port 6901** (see `backend/core/session_manager.py`).
- Serve the noVNC WebSocket at **`/websockify`** (default `CONTAINER_VNC_WS_PATH` in `backend/config.py`).
- Use workspace home **`/home/kuser`** so file list/upload in the UI match `backend/core/docker_manager.py`.

### Build

```bash
cd desktop-xfce
docker build -t airlock/bastion-desktop:latest .
```

### Import into Airlock

1. Admin UI → container templates → **Import template file (YAML/JSON)** and upload `desktop-xfce/bastion-desktop.airlock-template.yaml`, or
2. Adjust `docker_image` in that file if you use another tag, then import.

Ensure the Docker host can pull or already has the built image (same host that runs workspace containers).

### Quick manual check (optional)

After building, run a throwaway container on the default bridge with port publish only for local testing (Airlock itself uses `network_mode=none` then attaches the internal network):

```bash
docker run --rm -p 6901:6901 airlock/bastion-desktop:latest
```

From another shell, confirm something is listening on 6901; the full path is exercised when connecting through Airlock’s session WebSocket proxy.
