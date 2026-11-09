# CCS development container

The development container uses Ubuntu 24.04 with Node.js 24, Python 3, GTK 3,
MySQL client libraries, and the Codex CLI. Python packages from the repository's
`requirements.txt` are installed in `/opt/venv`. A MySQL 8.4 service runs beside
the application container and persists its data in a named volume.

## First-time setup

Create the local environment file and choose two development-only passwords:

```sh
cp .devcontainer/.env.example .devcontainer/.env
```

On macOS, install and start XQuartz, enable network clients, and allow the local
Docker connection:

```sh
defaults write org.xquartz.X11 nolisten_tcp -bool false
/opt/X11/bin/xhost +localhost
```

Restart XQuartz after changing `nolisten_tcp`. Then rebuild and open the
devcontainer. Its post-create script configures CCS, creates the database
schemas, and imports the CoCa MIB.

To check GTK forwarding from a terminal in the container:

```sh
python .devcontainer/gtk_smoke_test.py
```

## Codex app server

Codex listens on container port 4500 and is published only on the host loopback
interface at `ws://localhost:4501`. Login state persists in the
`ccs-codex-data` volume. Log in once from the repository root on the host:

```sh
docker compose -f .devcontainer/compose.yaml run --rm app codex login --device-auth
```

The application service waits for a successful login before starting the Codex
app server. Its WebSocket capability token is generated in
`.devcontainer/codex-ws-token`, which is ignored by Git. To supply a stable token
instead, define `CODEX_WS_TOKEN` in `.devcontainer/.env`.

## Useful commands

Start the services without the IDE:

```sh
docker compose -f .devcontainer/compose.yaml up --build
```

Reset only the development database by removing its named volume:

```sh
docker compose -f .devcontainer/compose.yaml down
docker volume rm chances-ccs_ccs-mysql-data
```

The exact Compose project prefix in the volume name can differ when the project
name is overridden. Removing the database volume permanently deletes its local
development data.
