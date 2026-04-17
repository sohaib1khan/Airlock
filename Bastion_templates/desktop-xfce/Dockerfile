# Airlock bastion desktop: XFCE + TigerVNC + websockify + PulseAudio (null sink), exposed for
# the control plane on TCP 6901 with WebSocket path /websockify (see CONTAINER_VNC_WS_PATH).
# Workspace files in the UI are rooted at /home/kuser (matches backend/core/docker_manager.py).
# Image is local-only — build with: docker compose build bastion-desktop

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8

# Ubuntu 22.04 ships Firefox as a snap only; use Mozilla's signed APT repo for a real deb.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
    && install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL https://packages.mozilla.org/apt/repo-signing-key.gpg \
       | gpg --dearmor -o /etc/apt/keyrings/packages.mozilla.org.gpg \
    && printf 'deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.gpg] https://packages.mozilla.org/apt mozilla main\n' \
       > /etc/apt/sources.list.d/mozilla.list \
    && printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1001\n' \
       > /etc/apt/preferences.d/mozilla \
    && apt-get update && apt-get install -y --no-install-recommends \
        dbus-x11 \
        ffmpeg \
        firefox-esr \
        netcat-openbsd \
        nginx \
        openssh-client \
        pavucontrol \
        pulseaudio \
        python3-pip \
        remmina \
        remmina-plugin-rdp \
        remmina-plugin-vnc \
        sudo \
        tigervnc-common \
        tigervnc-standalone-server \
        xdg-utils \
        xfce4 \
        xfce4-terminal \
    && pip3 install --no-cache-dir websockify==0.11.0 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash kuser \
    && mkdir -p /home/kuser/.vnc /home/kuser/workspace \
                /home/kuser/.config/xfce4 /home/kuser/.config/pulse \
    # xstartup: export XDG_RUNTIME_DIR so PulseAudio can create its socket, then
    # start PulseAudio (loads ~/.config/pulse/default.pa with null sink), then XFCE4.
    && printf '%s\n' \
        '#!/bin/sh' \
        'unset SESSION_MANAGER' \
        'unset DBUS_SESSION_BUS_ADDRESS' \
        'export XDG_RUNTIME_DIR=/run/user/$(id -u)' \
        '[ -r "$HOME/.Xresources" ] && xrdb "$HOME/.Xresources"' \
        'pulseaudio --start --exit-idle-time=-1 2>/dev/null || true' \
        'eval $(ssh-agent -s) > /dev/null 2>&1 || true' \
        'exec dbus-launch --exit-with-session startxfce4' \
        > /home/kuser/.vnc/xstartup \
    && chmod +x /home/kuser/.vnc/xstartup \
    # PulseAudio: null sink so Firefox/apps can play audio without physical hardware.
    # Audio is captured inside the container; wire up a streaming sink later if needed.
    && printf '%s\n' \
        '.include /etc/pulse/default.pa' \
        'load-module module-null-sink sink_name=airlock_sink sink_properties=device.description="Airlock-Desktop-Audio"' \
        'set-default-sink airlock_sink' \
        > /home/kuser/.config/pulse/default.pa \
    && printf '%s\n' \
        'exit-idle-time = -1' \
        > /home/kuser/.config/pulse/daemon.conf \
    # Firefox: register as default browser
    && printf '%s\n' \
        '[Default Applications]' \
        'text/html=firefox-esr.desktop' \
        'x-scheme-handler/http=firefox-esr.desktop' \
        'x-scheme-handler/https=firefox-esr.desktop' \
        > /home/kuser/.config/mimeapps.list \
    && printf '%s\n' \
        'WebBrowser=firefox-esr' \
        'TerminalEmulator=xfce4-terminal' \
        > /home/kuser/.config/xfce4/helpers.rc \
    && update-alternatives --install /usr/bin/x-www-browser x-www-browser /usr/bin/firefox-esr 200 \
    && update-alternatives --set x-www-browser /usr/bin/firefox-esr \
    && chown -R kuser:kuser /home/kuser

ENV BROWSER=/usr/bin/firefox-esr

RUN rm -f /etc/nginx/sites-enabled/default

COPY nginx-vnc.conf /etc/nginx/sites-enabled/airlock-vnc.conf
COPY entrypoint.sh /usr/local/bin/airlock-desktop-entrypoint.sh
RUN mkdir -p /usr/local/lib/airlock
COPY audio_server.py /usr/local/lib/airlock/audio_server.py
RUN chmod +x /usr/local/bin/airlock-desktop-entrypoint.sh

EXPOSE 6901

ENTRYPOINT ["/usr/local/bin/airlock-desktop-entrypoint.sh"]
