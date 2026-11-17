# Render deployment with SQLite

This deploys the existing project as **one Docker web service**: Nginx → PHP-FPM/Laravel → loopback-only FastAPI/MobileNetV2. No Render Postgres, Redis or second AI service is created. The browser never accesses the Python port directly.

## Cost and durability: choose one

**Recommended: `render.yaml`.** One paid `1c-2g` compute instance (2 GB RAM) and a 1 GB persistent disk mounted at `/var/data`. SQLite and its generated application key survive restarts/redeploys. This avoids paying for a Postgres database, **not all hosting costs**. Check the prices shown by Render before creating resources. The RAM recommendation is a starting point, not a measured cloud capacity guarantee; PyTorch and full-resolution leaf images can use substantial memory.

**Optional: `render.demo.yaml`.** Free compute, no disk. It is only a temporary experiment: SQLite, sessions and the generated key disappear on restart/redeploy/spin-down. Render free instances currently have 512 MiB RAM and spin down when idle. This may be insufficient for the combined Python/PHP application; free deployment is not promised to work. Do not rely on it for a presentation without testing. If the logs show out-of-memory/SIGKILL, increase RAM, not the timeout.

Use **one** Blueprint, not both. Neither has a `databases:` section.

## Deploy through the Render dashboard

1. Ensure `Dockerfile`, `.dockerignore`, `deploy/`, `render.yaml`, `package-lock.json`, and the associated Laravel health/HTTPS changes are pushed to `feature/crop-detection-foundation` in the existing repository.
2. Sign in at https://dashboard.render.com and connect the GitHub account/repository `nahsir12390/crop-disease-detection`.
3. Choose **New → Blueprint**, select the existing repository and branch, and use Blueprint path **render.yaml**. To deliberately try the temporary option instead, select **render.demo.yaml**.
4. Inspect the proposed compute/disk costs and create the resources only when you accept them. This preparation has not created any Render resources or incurred Render charges.
5. Leave the root directory at the repository root. Runtime is Docker; Dockerfile path is `./Dockerfile`. Do not add Node/Python native-runtime build/start commands or a pre-deploy migration command.
6. The Docker build installs CPU PyTorch, PHP dependencies and frontend assets, then downloads and actually loads the pinned model. A failed model download/load fails the image build instead of producing fabricated predictions.
7. At container startup, the entrypoint initializes missing SQLite/key files, caches runtime configuration, runs migrations against the mounted disk, validates Nginx and starts the three managed processes.
8. Wait for Render to mark **Live**. Open the HTTPS URL supplied by Render. `/healthz` must return `{"status":"ready"}`. `/up` is basic Laravel liveness; it alone does not establish AI readiness.
9. Select Maize and upload a real leaf. Verify the preview, results and top matches. Remember the model's measured field accuracy is 45%; successful hosting does not improve that accuracy.

Auto-deploy is deliberately **off** in the Blueprints. After reviewing a code update, use **Manual Deploy → Deploy latest commit**. This avoids unintended redeploys during a presentation. Do not merge into `main` just to deploy: the feature branch is explicitly selected.

## Environment variables

The image and Blueprint supply production defaults:

| Variable | Value / behavior |
| --- | --- |
| APP_ENV / APP_DEBUG | production / false |
| DB_CONNECTION | sqlite, enforced by startup |
| DATA_DIR / DB_DATABASE | /var/data / /var/data/database.sqlite |
| SESSION_DRIVER / CACHE_STORE | database / database; migrated automatically |
| QUEUE_CONNECTION | sync; no queue worker needed |
| CROP_AI_URL | http://127.0.0.1:8001; internal API, no public URL needed |
| PORT | Provided by Render; defaults to 10000 locally |
| APP_URL | Automatically taken from RENDER_EXTERNAL_URL unless explicitly set |
| FORCE_HTTPS / SESSION_SECURE_COOKIE | true / true |
| TRUSTED_PROXIES | `*` for this Render-managed reverse-proxy deployment only; unset locally |
| HF_HOME / HF_HUB_OFFLINE | /opt/models / 1; verified model baked into image |
| APP_KEY | Optional explicit Laravel base64 key; otherwise generated once and saved at /var/data/app.key |

No `.env` or credentials are copied into the image. No APP_KEY is embedded at build time. For the persistent configuration, you do not need to type a key: it is created on the mounted disk and reused. Never publish, log or casually change it. If you choose to supply APP_KEY yourself, use a genuine Laravel AES-256 key (`base64:` plus 32 random bytes); Render's generic random-string generator is not automatically a correctly formatted Laravel key.

For a custom domain, set APP_URL to its complete HTTPS origin, e.g. `https://crop.example.com`, then redeploy. With the default onrender.com domain, Render supplies the URL automatically. HTTPS form/health URLs and secure cookies are required to avoid mixed-content and session/CSRF errors.

## Persistent SQLite rules

- The disk path must be `/var/data`, matching the Blueprint. Data outside that mount is ephemeral. Do not mount the whole `/app` directory over the source.
- Keep one instance. A local SQLite database on one mounted disk is not a shared, horizontally scalable database. Disk-backed deploys can involve a short interruption.
- The entrypoint creates a database **only if absent**. It never truncates or reseeds an existing one and never uses `migrate:fresh`.
- Migrations run at runtime because the disk is not available during builds or pre-deploy jobs.
- The database uses a busy timeout and WAL mode. If backing it up live, use SQLite's backup API; copying only database.sqlite while WAL is active can omit transactions. Keep an off-service copy of the database and application key for anything important.
- Uploaded leaf photos and result history are not permanently saved by the current application. SQLite mainly stores standard Laravel/session/cache tables.

## Security and resource limits

Nginx exposes only the public `$PORT`; FastAPI is bound to 127.0.0.1:8001 and PHP-FPM to 127.0.0.1:9000. PHP execution is limited to the Laravel front controller. Production errors go to logs, not the browser. No user-uploaded files are executable. Nginx/PHP/Laravel all enforce compatible upload limits.

There is one AI worker, bounded numerical thread counts, and three on-demand PHP workers. This is a low-volume prototype deployment, not a load-tested public diagnosis service. Monitor actual memory/CPU usage before inviting many users. Sessionless readiness checks verify both SQLite connectivity and a genuinely ready model, returning 503 while unavailable.

## Local Docker verification (requires Docker Desktop or Linux Docker)

```powershell
docker build -t crop-disease-render .
docker volume create crop-disease-data
docker run --name crop-disease-demo -d -p 10000:10000 --mount source=crop-disease-data,target=/var/data -e APP_URL=http://localhost:10000 -e FORCE_HTTPS=false -e SESSION_SECURE_COOKIE=false crop-disease-render
```

Open http://localhost:10000 and http://localhost:10000/healthz. Those three HTTP overrides are for local Docker testing only; keep HTTPS enabled on Render. Internal AI ports need not be published. Then test persistence with `docker restart crop-disease-demo`: the key/database should be reused.

The preparation machine has no Docker daemon or installed WSL distribution, so an image build cannot be claimed as locally verified here. Laravel regression/health tests and static configuration checks can run locally. The optional Docker smoke workflow provides a Linux build/start/prediction/restart check when run in GitHub Actions; check its actual result before claiming container verification.

## Troubleshooting

| Problem | Check |
| --- | --- |
| Dockerfile or package-lock missing | Commit/push the deployment files and the lockfile; select the feature branch and repository root. |
| Model files cannot download | Build logs and Hugging Face connectivity; the build must succeed before deployment. |
| No open port | Nginx logs and PORT; do not override the Docker command. |
| /healthz is 503 | AI initialization and SQLite startup logs; a reachable `/up` is not enough. |
| SQLite permissions / missing tables | Disk mount `/var/data`, DATA_DIR/DB_DATABASE alignment and migration logs. |
| APP_KEY / cookie / 419 CSRF error | Key must be stable, APP_URL must match the HTTPS domain, proxy trust/secure cookies must stay enabled. Refresh stale sessions after switching hosts. |
| Out of memory / killed Python process | Increase compute RAM. The free 512 MiB plan is not a verified fit. |
| Data disappears after restart | The free demo has no persistent disk; use the persistent Blueprint for durable data. |

## Render sources checked 17 November 2026

- https://render.com/docs/docker
- https://render.com/docs/disks
- https://render.com/docs/free
- https://render.com/docs/health-checks
- https://render.com/docs/environment-variables
- https://render.com/docs/blueprint-spec
