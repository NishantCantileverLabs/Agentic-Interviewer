# Judge0 (T4)

Self-hosted Judge0 for sandboxed code execution, wrapped entirely by the backend's
`POST /execute` (the backend never exposes Judge0 directly).

Enable with `docker compose --profile sandbox up` once T4 adds the service definitions
here (Judge0 needs its own server + workers + db + redis containers and a pinned
version ≥ 1.13.1 for cgroup-v2 compatibility under Docker Desktop/WSL2).

Limits (from .env): 5s CPU, 256MB memory, no network egress, 64KB output truncation.
