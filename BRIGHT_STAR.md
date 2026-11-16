# BRIGHT_STAR.md — Bright Agent run instructions for OWASP Juice Shop

Run-memory and operator instructions for Bright Agent (STAR). Juice Shop is a single
Node.js process backed by a file-based SQLite database, so under scan load it needs an
init process, an automatic restart policy, and resource caps to stay healthy. Build and
run it with the hardened wrapper below so it survives a full scan. All of this works with
Juice Shop's own source as-is.

## Startup

Build the application from this repository's own `Dockerfile`, wrapped in a hardened
Compose file. The wrapper is what keeps the target alive under load. Write the following
to `docker-compose.dast.yml` at the repo root and recreate it per run, then
`docker compose -f docker-compose.dast.yml up -d --build`:

```yaml
services:
  juice-shop:
    build:
      context: .                              # build from the repo's own Dockerfile
      dockerfile: Dockerfile
      args:
        # v7 omits an XML writer needed by this Dockerfile's SBOM step.
        CYCLONEDX_NPM_VERSION: "6.0.1"
    init: true                                # PID-1 init reaps zombies, forwards signals
    restart: unless-stopped                   # a single crash auto-recovers; the scan continues
    ports:
      - "3000:3000"
    environment:
      NODE_ENV: unsafe                        # keep all challenges active
      NODE_OPTIONS: "--max-old-space-size=1536"  # V8 heap below the container cap: GC/throw instead of OOM-kill
      NODE_CONFIG: '{"ctf":{"countryMapping":{"scoreBoardChallenge":{"name":"Test","code":"ZZ"}}}}'
    mem_limit: 2g
    memswap_limit: 2g                         # no swap thrash
    cpus: "2.0"
    pids_limit: 512
    ulimits:
      nofile:
        soft: 65536
        hard: 65536
    healthcheck:
      test: ["CMD", "/nodejs/bin/node", "-e", "require('http').get('http://127.0.0.1:3000/rest/admin/application-version',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 90s
    tmpfs:
      - /juice-shop/logs:uid=65532,gid=65532
```

Two settings match this repo's distroless-based `Dockerfile` (base
`gcr.io/distroless/nodejs22-debian12`, `USER 65532`):

- The healthcheck invokes `/nodejs/bin/node` by absolute path, where the distroless image
  keeps the Node binary.
- The `tmpfs` logs mount sets `uid=65532,gid=65532` to match the container's non-root
  user, so the app can write `logs/`.

Keep these two values aligned with the `Dockerfile`'s base image and user.

Readiness: the target is up once `GET /rest/admin/application-version` returns HTTP 200.
First boot rebuilds and re-seeds the database, which takes ~60–90 s — wait for the 200
before scanning (this is why `start_period` is 90 s).

The application creates its schema and seed users on every start. It has no installation
wizard. `/install` is the Angular SPA fallback, not a setup page. During
`first_run_setup`, verify the existing admin login and report the app as already set up.
Do not add users, edit seed files, or rebuild the image during that phase.

Every Docker rebuild must pass `CYCLONEDX_NPM_VERSION=6.0.1`. The unpinned current
v7 release fails this repository's XML SBOM step. Local clean-master builds and the
resulting health endpoint were verified with v6.0.1.

## Auth

- Run with `RUN_MODE=full` and `BRIGHT_AUTH_STUB=on`.
- Require the transient auth stub for the live application scan.
- Use the agent-managed `X-Bright-Principal` secret as the scan identity.
- If app startup or stub setup fails, stop the run with an error.
- Never start, switch to, or continue in function harness mode.
- Session check: `GET /rest/basket/1` returns 401 anonymously and 200 with
  the privileged stub session.
- Never print or persist the stub secret.

## Credentials

Accounts in `data/static/users.yml` are public fixtures for setup checks and role
context only. Do not replace the required auth stub with a real login session.

## Route inventory and baseline examples

Read `bright-star-route-hints.openapi.yml` before building the route inventory or
sampling parameters. It is a source-backed supplement to the B2B-only `swagger.yml`.

- `server.ts` declares 13 `finale.resource` models.
- Each model generates exactly collection GET/POST and item GET/PUT/DELETE.
- The catalog therefore contains exactly 65 generated CRUD operations.
- It marks 27 operations as safe and locally baseline-verified.
- It maps all 22 exclusions from run 41988468812 to valid requests or exclusions.
- Do not invent PATCH operations or add `/api` to direct routes.
- Resolve MarsDB order and review IDs through the catalog's resolver requests.
- Keep operations marked `x-bright-register: false` out of registration.

## Scan configuration (apply at scan launch)

Set the following in the scan-launch configuration (Bright API / `bright-cli` / scan
template). `BRIGHT_STAR.md` carries structured startup / auth / credentials / infra
instructions; scope and concurrency belong to the scan launch config, so configure them
there:

- **Exclude the authentication endpoint `POST /rest/user/login` from the attack scope.**
  Fuzzing it corrupts the request the auth session is minted from, which breaks scan-wide
  authentication. Keep read-only auth endpoints such as `GET /rest/user/whoami` in scope.
- **Exclude `/socket.io/` long-polling endpoints.** They hold connections open to the
  Repeater's request timeout; under scan load this can drop the Repeater↔cloud bridge and
  pause the scan. They are transport, not a useful attack surface here.
- **Re-authenticate on a genuine expired-session signal only (HTTP 401), not on 403.**
  Juice Shop returns 403 as a normal "authenticated but not allowed" response on many
  protected routes; treating 403 as session loss triggers unnecessary re-logins.
