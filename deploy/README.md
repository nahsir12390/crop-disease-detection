# Render deployment: free temporary SQLite demo

The default `render.yaml` deploys the existing project as **one free Docker web service**, with SQLite and no persistent disk. This follows the requested temporary-demo approach: data/session resets on rebuild/restart/spin-down are accepted. No Postgres resource or separate AI service is required.

The container runs Nginx, PHP-FPM/Laravel and loopback-only FastAPI/MobileNetV2. The verified model files are baked into the Docker image, so a container restart does not need to download the model again. SQLite is initialized and migrated automatically when absent.

## Deploy on Render

The site now includes registration/login and an administrator dashboard. Before deploying, see [account and admin setup](../docs/accounts-and-admin.md). Set optional `ADMIN_EMAIL` and `ADMIN_PASSWORD` in Render to provision the owner's administrator automatically; no shell is needed. Contact messages are stored in the temporary SQLite database. The public home page remains accessible, and leaf analysis requires login.

1. Open https://dashboard.render.com and choose **New ? Blueprint**.
2. Connect the existing GitHub repository `nahsir12390/crop-disease-detection`.
3. Select branch **feature/crop-detection-foundation**, Blueprint path **render.yaml**, and the repository root directory.
4. Review the proposed service. The default is **Free**, with no disk and no Postgres database. Create the service when ready; preparing/pushing these files has not created a Render service.
5. Leave Dockerfile path `./Dockerfile`. Do not add native Node/Python build/start commands or override the Docker command.
6. Wait for the Docker build. It installs dependencies, compiles frontend assets, downloads the pinned model and performs an actual model warm-up. A failed download/load fails the build.
7. Startup creates missing SQLite/key files, runs migrations, and starts the managed services. Render waits for `/healthz` to report ready.
8. When Live, open the HTTPS URL Render provides. Select Maize, upload a real photo and verify results. The AI port is internal; do not configure a second public API URL.

No manually entered environment variables or model account/API key are required for the default onrender.com domain. `APP_URL` is taken from Render's `RENDER_EXTERNAL_URL`; an application key is generated at startup and saved with the temporary database. For a custom domain, set `APP_URL` to the exact HTTPS origin and redeploy.

Auto-deploy is deliberately **off**. After reviewing an update, use **Manual Deploy ? Deploy latest commit**. Deploy the feature branch directly; merging into main is unnecessary.

## Free-instance limits

The default has no persistent storage: SQLite, session files and the generated application key reset when Render replaces the container. Refresh an old browser page after a restart if it has a stale CSRF/session token. There are no permanent diagnosis records or uploaded-photo history in the current application.

The public model itself stays in the Docker image and loads offline on each boot. First image builds still require Hugging Face and package-download connectivity.

Render's free size is currently 512 MiB RAM and 0.1 CPU, and idle services spin down. A separate CI check assesses those resource limits, but one small upload is not a load/capacity guarantee for large field photos or concurrent visitors. Inspect the **free-sized check's own result**, not just an overall green workflow: that assessment is non-blocking. If Python is killed/out-of-memory, increase compute RAM or use a separately hosted AI service. Increasing timeouts does not fix a memory shortage.

## Optional durable configuration

If persistence is wanted later, use **render.persistent.yaml** instead. It selects a paid `1c-2g` instance and a 1 GB disk at `/var/data`, still without Postgres. It stores SQLite and the generated key there and uses database-backed sessions/cache. Review Render's current compute/disk charges before choosing it. Use one Blueprint, not both.

Do not mount over `/app`. Keep one instance: SQLite on a mounted disk is not a horizontally shared database. Migrations run at startup because the disk is unavailable during builds/pre-deploy jobs. Existing databases are never truncated and `migrate:fresh` is never used.

For important persistent data, use SQLite's backup API and keep an off-service copy of the database and key. Copying only database.sqlite while WAL is active can omit transactions.

## Runtime configuration

| Setting | Default / behavior |
| --- | --- |
| APP_ENV / APP_DEBUG | production / false |
| DB_CONNECTION / DB_DATABASE | sqlite / /var/data/database.sqlite |
| DATA_DIR | /var/data; temporary on free, mounted disk in optional persistent setup |
| SESSION_DRIVER / CACHE_STORE | file / file on free; database / database in persistent option |
| QUEUE_CONNECTION | sync; no worker required |
| CROP_AI_URL | http://127.0.0.1:8001, internal only |
| PORT | Set by Render; default 10000 locally |
| APP_URL | Render's public URL unless explicitly supplied |
| FORCE_HTTPS / SESSION_SECURE_COOKIE | true / true on Render |
| TRUSTED_PROXIES | `*` for the Render-managed reverse proxy, unset in local development |
| HF_HOME / HF_HUB_OFFLINE | /opt/models / 1; pinned model baked into image |
| APP_KEY | Optional explicit valid Laravel key; otherwise generated and stored at /var/data/app.key |

No local .env or credentials are copied into the image. A supplied APP_KEY must be a genuine Laravel AES-256 key (`base64:` plus 32 random bytes), not an arbitrary random string. Keep it stable if opting into persistent data.

Nginx exposes only Render's public port. Python binds 127.0.0.1:8001; PHP-FPM binds 127.0.0.1:9000. PHP execution is limited to the Laravel front controller. The 5 MiB upload limit is reflected in Nginx/PHP/Laravel. HTTPS form/health URLs and proxy-aware secure cookies avoid mixed-content/session problems.

`/up` checks Laravel liveness only. `/healthz` checks SQLite connectivity and actual AI readiness, returning 503 while unavailable; it does not create database sessions. Production errors are logged instead of shown in the browser. The model's previously measured 45% maize field accuracy is unchanged by deployment.

## Docker verification

Verified on 17 November 2026 in [GitHub Actions run 44103724935](https://github.com/nahsir12390/crop-disease-detection/actions/runs/44103724935), using commit `b711a7a`:

- Linux Docker build, dependency checks, pinned model loading and warm-up passed.
- Both the standard container check and the separate **512 MiB / 0.1 CPU** check passed readiness and a real, CSRF-protected photo upload through Laravel to MobileNetV2.
- Memory sampled after prediction was **321.9 MiB / 512 MiB** in the constrained check. This is a sample, not peak memory or a concurrent-load measurement.
- SQLite contents and the generated key survived restart with the test volume. The free Render configuration does **not** attach that volume and does not promise persistence.

These checks verify the container, not a live Render deployment. After creating the Render service, verify its public HTTPS URL and upload a real image there. Larger uploads and simultaneous users still need capacity testing.

This preparation machine has no Docker daemon/WSL installation. Linux verification runs in `.github/workflows/render-docker.yml`: image build/model warm-up, a real photo upload through Laravel, and SQLite/key preservation when restarting a container with a test volume. The independent free-sized assessment caps memory at 512 MiB and CPU at 0.1. These are real inference checks, not mocked predictions. Check their actual results before claiming a size is verified.

With Docker available locally:

```powershell
docker build -t crop-disease-render .
python deploy/smoke_test.py --image crop-disease-render
python deploy/smoke_test.py --image crop-disease-render --memory 512m --cpus 0.1
```

The script uses Python's standard library, creates randomly named test resources, and cleans up only its own container/volume. It does not target an existing user service.

For a manual browser test:

```powershell
docker run --name crop-disease-demo -d -p 10000:10000 -e APP_URL=http://localhost:10000 -e FORCE_HTTPS=false -e SESSION_SECURE_COOKIE=false -e SESSION_DRIVER=file -e CACHE_STORE=file crop-disease-render
```

Open http://localhost:10000. Those HTTP overrides are local-test-only; keep HTTPS settings on Render.

## Troubleshooting

- Missing Dockerfile/lockfile: check the selected branch, repository root and pushed files.
- Build/model-download failure: inspect build logs and connectivity; do not ignore a failed warm-up.
- No listening port: inspect Nginx/startup logs; leave the Docker command unchanged.
- `/healthz` returns 503: inspect AI initialization and SQLite startup logs; a reachable `/up` is not enough.
- Wrong redirect or 419 CSRF: APP_URL must be the exact public HTTPS origin, with secure cookies and Render proxy trust. Refresh stale sessions after restarts.
- Python killed or out of memory: check the free-sized CI assessment and actual Render memory; increase RAM if needed.
- Data reset: expected on the requested free temporary configuration.

References checked 17 November 2026: https://render.com/docs/docker, https://render.com/docs/free, https://render.com/docs/disks, https://render.com/docs/health-checks, https://render.com/docs/environment-variables and https://render.com/docs/blueprint-spec.
