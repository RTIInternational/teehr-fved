# Run The `wsf-inference` Prefect Workflow Locally (KinD)

End-to-end runbook: stand up the local KinD + Garden stack, stage the trained
model assets in the in-cluster S3, and execute the three deployments
(`wsf-inference-oshbocker-1st`, `-ckua-2nd`, `-rasyidstat-3rd`) as real Prefect
flow runs on a local Kubernetes worker. Complements `teehr-cloud-core/README.md`
(platform).

Run the steps **in order**; several only work after an earlier one (called out
inline). Commands run from the repo root (`teehr-fved/`) unless stated. Only the
Prefect-related services are deployed (no Keycloak/JupyterHub/Trino), which
keeps RAM use manageable.

## Overview

| # | Step | Why it must come here |
|---|---|---|
| 0 | Prerequisites | tools, Docker config, line endings, assets, keys |
| 1 | Create the KinD cluster | everything else deploys onto it |
| 2 | Put `/data` on a Linux filesystem (WSL/`/mnt/c` only) | before any flow pod writes to it |
| 3 | Configure secrets and WSF variables | read at deploy time |
| 4 | Deploy (4 Garden commands) | creates S3, Prefect, storage, service account |
| 5 | Stage assets in local S3 | S3 exists only after step 4 |
| 6 | Prefect CLI/API access | needs the Prefect server from step 4 |
| 7 | Pre-flight: check upstream data sources | avoid 40-minute runs that die on a 502/429 |
| 8 | Run the models, one at a time | |
| 9 | Check results | |

## 0. Prerequisites

| Need | Notes |
|---|---|
| x86_64 Linux / WSL2 | `Dockerfile.prefect-wsf` only builds on amd64. |
| Docker engine | Give it >= 12 GB RAM and ~40 GB free disk. Verify with `docker run --rm hello-world`. |
| `kind`, `kubectl`, `uv`, `aws` (CLI v2) | `uvx --from awscli aws ...` works if `aws` is missing. |
| `garden` 0.13.x | `brew install garden-io/garden/garden-cli`; `garden version` (known-good 0.13.54). |
| Trained model assets | NOT in git; obtain from the model maintainers (see 0.4). |
| Copernicus CDS key | Only for `rasyidstat_3rd` strict mode; accept the ERA5-Land and SEAS5 licences at cds.climate.copernicus.eu. Stored in `~/.cdsapirc`. |
| Free ports 80/443 | KinD publishes them for ingress. |
| Internet access | Models download live data; see step 7 for what can go wrong. |

### 0.1 Line endings (Windows checkouts)

If the repo was checked out from Windows with CRLF conversion, shell scripts
fail with `cannot execute: required file not found` (the shebang is
`/bin/sh\r`). Check and fix **both** the main repo and the submodule:

```bash
file teehr-cloud-core/kind/create_kind_cluster.sh     # "with CRLF line terminators" = bad
cd teehr-cloud-core
git config core.autocrlf input && git config core.eol lf
git diff --ignore-cr-at-eol --stat | tail -1          # empty = only line endings differ, safe to reset
git rm --cached -r -q . && git reset --hard -q        # re-checkout with LF
chmod +x kind/create_kind_cluster.sh scripts/*.sh
cd ..
```

Do not use `reset --hard` if the `--ignore-cr-at-eol` diff shows real edits.
Cloning inside the WSL filesystem (`~/repos`) avoids this and the `/mnt/c`
problems in step 2.

### 0.2 Docker credential helper (Docker engine in WSL)

If `docker pull` fails with
`error getting credentials ... docker-credential-desktop.exe not found`, the
config still points at Docker Desktop:

```bash
cat ~/.docker/config.json            # {"credsStore": "desktop.exe"} = the problem
cp ~/.docker/config.json ~/.docker/config.json.bak && echo '{}' > ~/.docker/config.json
docker pull registry:2
```

### 0.3 Hostnames (optional)

Everything below uses `kubectl port-forward`, so no hosts entries are needed.
Add `127.0.0.1 prefect.teehr.local.app.garden s3.teehr.local.app.garden` to
`/etc/hosts` only if you want the ingress URLs.

### 0.4 Model assets

Stage them in `~/wsf-assets/<model>/...`, files at the root of each model
directory (no extra directory level), exactly as listed in each
`assets.sha256`:

```text
~/wsf-assets/oshbocker_1st/{models,feature_parameters}/...
~/wsf-assets/ckua_2nd/results/forecast/...
~/wsf-assets/rasyidstat_3rd/models/...
```

Verify checksums now (from the repo root; any mismatch is printed, and each
model should end with `exit=0`):

```bash
REPO=$PWD
for m in oshbocker_1st ckua_2nd rasyidstat_3rd; do
  (cd ~/wsf-assets/$m && sha256sum -c --quiet "$REPO/prefect-workflows/wsfr_inference/$m/assets.sha256"; echo "$m exit=$?")
done
```

## 1. Create the KinD cluster

```bash
git submodule update --init teehr-cloud-core
./teehr-cloud-core/kind/create_kind_cluster.sh
kubectl config current-context            # must be: kind-kind
kubectl get nodes                         # 1 control-plane + 3 workers, all Ready
kubectl -n projectcontour get pods        # wait until Running
```

If an earlier attempt half-created things: `docker rm -f kind-registry; kind delete cluster`, then re-run.
The script also starts a local image registry (`kind-registry`, `localhost:5001`).

## 2. Put `/data` on a Linux filesystem

The script bind-mounts `teehr-cloud-core/data` into each node as `/data`; the
flow pods (UID 1000) cache assets and working files in `/data/wsf` (PVC
`data-nfs`).

- **Repo on the WSL ext4 filesystem:** just `chmod -R a+rwx teehr-cloud-core/data`.
- **Repo under `/mnt/c` (Windows drive, 9p/NTFS):** the model `build` stage fails
  with `shutil.Error ... [Errno 1] Operation not permitted`, and the drive may
  be nearly full. Bind-mount a Linux directory over `/data` on the node that
  runs flow pods:

  ```bash
  docker exec kind-worker3 sh -c 'mkdir -p /var/wsf-data && chmod 777 /var/wsf-data && mount --bind /var/wsf-data /data'
  docker exec kind-worker3 df /data | tail -1       # should be a Linux device, not "C:\"
  ```

  **Redo this after any Docker/WSL restart**, before running flows. Cached
  assets and working files live inside the node container; they are removed with
  the cluster.

The local PVC is only 10Gi, which is enough for single-site test runs.

## 3. Configure secrets and WSF variables

### 3.1 CDS credentials (third model only)

Create the git-ignored `teehr-cloud-core/secrets/secrets.local.private.yaml`
(layered over `secrets.local.yaml`). Keep the other `prefect-workflow-secrets`
keys as placeholders: the `load-secrets` job reads them as required, and the
test doesn't use them. Build the file from `~/.cdsapirc` without printing the key:

```bash
python3 - <<'EOF'
import os
cfg = dict(l.strip().split(":", 1) for l in open(os.path.expanduser("~/.cdsapirc")) if ":" in l and not l.startswith("#"))
ph = ["api-usgs-pat", "crmms-esp-password-format", "m3works-aws-access-key-id",
      "m3works-aws-secret-access-key", "cu-swe-aws-access-key-id", "cu-swe-aws-secret-access-key"]
out = "secrets:\n  prefect-workflow-secrets:\n    data:\n"
out += "".join(f"      {k}: CHANGE_ME_{k.upper().replace('-', '_')}\n" for k in ph)
out += f'      cdsapi-url: "{cfg["url"].strip()}"\n      cdsapi-key: "{cfg["key"].strip()}"\n'
open("teehr-cloud-core/secrets/secrets.local.private.yaml", "w").write(out)
EOF
```

Skip this if you only run models 1 and 2. Never commit the file.

### 3.2 S3 locations

In `project.garden.yml` (local edit, don't commit), replace the empty `wsf`
defaults:

```yaml
variables:
  wsf:
    assetsS3Uri: "s3://warehouse/wsf/assets"
    outputS3Uri: "s3://warehouse/wsf/outputs"
```

The in-cluster S3 (RustFS, `http://local-s3:9000`, `localadmin` /
`localadmin123`) is created with one bucket, `warehouse`; use prefixes in it.
The flow reads the endpoint from `REMOTE_CATALOG_S3_ENDPOINT`, which the local
environment injects along with the S3 credentials.

## 4. Deploy

`prefect-workflow-deploy` does **not** pull in the service account or the
storage claim the flow pods need, so deploy all four:

```bash
garden deploy prefect-workflow-deploy --env local   # builds images (slow first time), Prefect server/worker, secrets, registers the 3 deployments
garden deploy prefect-job-sa --env local            # ServiceAccount prefect-job used by flow-run pods
garden deploy local-storage --env local             # PV/PVC data-nfs (/data)
garden deploy local-s3-deploy create-local-s3-bucket --env local   # only if `kubectl -n teehr-hub get svc local-s3` is missing
```

Verify:

```bash
kubectl -n teehr-hub get pods                 # prefect-server, prefect-worker, prefect-pg, local-s3 Running
kubectl -n teehr-hub get sa prefect-job
kubectl -n teehr-hub get pvc data-nfs         # Bound
kubectl -n teehr-hub get svc local-s3
```

The registration job (`deploy-prefect-workflows`) is deleted 60s after it
finishes, so `kubectl logs job/...` usually finds nothing; verify registration
in step 6 instead. After changing `wsf.*`, secrets or code under `workflows/` or
`wsfr_inference/`, redeploy with `garden deploy prefect-workflow-deploy --env local`
(add `--force` for variable changes).

## 5. Stage assets in local S3

```bash
kubectl -n teehr-hub port-forward svc/local-s3 9000:9000 &     # leave running
export AWS_ACCESS_KEY_ID=localadmin AWS_SECRET_ACCESS_KEY=localadmin123 AWS_DEFAULT_REGION=us-east-1
for m in oshbocker_1st ckua_2nd rasyidstat_3rd; do
  aws --endpoint-url http://localhost:9000 s3 sync ~/wsf-assets/$m s3://warehouse/wsf/assets/$m
done
aws --endpoint-url http://localhost:9000 s3 ls s3://warehouse/wsf/assets/ --recursive | wc -l   # expect 128
```

If `aws` complains about bucket addressing: `aws configure set default.s3.addressing_style path`.
A wrong layout fails clearly in the flow's `check-assets` stage.

## 6. Prefect CLI/API access

The Prefect UI behind the ingress needs Keycloak (not deployed), so talk to the
server directly. Use a **separate terminal** for these commands and leave the
port-forward running (it prints "Handling connection for 4200" - normal).

```bash
# terminal A
kubectl -n teehr-hub port-forward svc/prefect-server 4200:4200

# terminal B
export PREFECT_API_URL=http://localhost:4200/api
# importlib_metadata is an undeclared dependency of prefect 3.4.24 (matches the server image)
alias prefect='uvx --python 3.12 --from prefect==3.4.24 --with importlib_metadata prefect'
prefect deployment ls | grep wsf              # expect the 3 deployments
prefect work-pool ls                          # kubernetes-pool
```

Aliases last for the shell session; run `type prefect` to check what it expands to.

**Optional dashboard:** the server's UI is configured for the ingress URL, so
http://localhost:4200 shows "Unable to connect to Prefect server". Point it at
the port-forward (temporary; a later `garden deploy` reverts it):

```bash
kubectl -n teehr-hub set env deploy/prefect-server PREFECT_UI_API_URL=http://localhost:4200/api
kubectl -n teehr-hub rollout status deploy/prefect-server
# restart the port-forward, then hard-refresh http://localhost:4200
```

## 7. Pre-flight: check upstream data sources

Runs download live data, and a dead upstream only shows up after a long
`download` stage. Probe first:

```bash
python3 prefect-workflows/wsfr_inference/check_data_sources.py
curl -s -o /dev/null -w 'NRCS %{http_code}\n' "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets=*:*:SNTL&activeOnly=true"
curl -s -o /dev/null -w 'USGS %{http_code}\n' "https://api.waterdata.usgs.gov/ogcapi/v1/collections/daily/items?monitoring_location_id=USGS-12362500&parameter_code=00060&limit=1"
```

Do not start runs unless both return `200`:

- **NRCS AWDB (`wcc.sc.egov.usda.gov`)** is used by all three models. A 502 there
  is an upstream outage and fails every model in `download` (the third model
  retries for about 40 minutes first). Wait for recovery.
- **USGS Water Data API** rate-limits anonymous callers per source IP (HTTP 429,
  "obtain an API token"). Shared office/VPN IPs and running several models at
  once exhaust it. Wait for the window to reset. The flow currently has no
  USGS token pass-through; if 429s persist, request a free key
  (api.waterdata.usgs.gov/signup) and add `API_USGS_PAT` loading to
  `workflows/models/wsf_forecasts.py` (`model_environment`, same pattern as the
  CDS secrets) with the key in the `api-usgs-pat` secret.

## 8. Run the models (one at a time)

Run sequentially: all flow pods share one node, one 10Gi volume and one public
IP (so one USGS/NRCS rate-limit budget). The deployments' concurrency limit is
per deployment, so nothing stops you running different models together - don't.

Use an issue date between January and July and one site for the first pass.
`--watch` blocks until the run finishes:

```bash
prefect deployment run wsf-inference/wsf-inference-ckua-2nd \
  --param issue_date=2026-04-01 --param sites='["libby_reservoir_inflow"]' --watch

prefect deployment run wsf-inference/wsf-inference-oshbocker-1st \
  --param issue_date=2026-04-01 --param sites='["libby_reservoir_inflow"]' --watch

prefect deployment run wsf-inference/wsf-inference-rasyidstat-3rd \
  --param issue_date=2026-04-01 --param sites='["libby_reservoir_inflow"]' --watch
```

Notes:
- Site IDs come from each package's `static/metadata.csv`; omitting `sites` runs
  all eligible sites (much slower). If a model rejects the site, pick another.
- `rasyidstat_3rd` is strict by default and needs CDS credentials and
  ERA5-Land/SEAS5 data for the issue date; past dates are normally fine.
  `--param strict_ensemble=false` allows a partial ensemble. Without credentials
  it fails immediately with "requires CDSAPI_URL/CDSAPI_KEY".
- The first start pulls the ~3 GB WSF image onto the node (about a minute) and
  the first run per model copies assets from S3 into `/data/wsf/assets/`.
- Stages: `check-assets`, `build`, `download` (slow), [`preprocess` for the 3rd],
  `predict`.

Monitor (pod names are `<flow-run-name>-<suffix>` and change every run):

```bash
prefect flow-run ls --limit 5                                  # PENDING / RUNNING / COMPLETED / FAILED
kubectl -n teehr-hub get pods --sort-by=.metadata.creationTimestamp | grep -v "pg\|prefect-server\|prefect-worker\|local-s3"
kubectl -n teehr-hub logs -f $(kubectl -n teehr-hub get pods -o name | grep <flow-run-name>)
prefect flow-run logs <flow-run-id> | tail -50                  # works after the pod is gone
```

A run stuck in `PENDING/Submitting` means the pod can't start:
`kubectl -n teehr-hub get events --sort-by=.lastTimestamp | tail`.

## 9. Check the results

Each attempt archives to
`s3://warehouse/wsf/outputs/<solution>/<issue-date>/<flow-run-id>/<attempt-id>/`
(`forecast.csv`, `run.json`, `logs/<stage>.log`). It is a published forecast
only if `run.json` says `"status": "succeeded"`. Failed attempts archive
`status: failed` plus the stage logs. With the port-forward and AWS variables
from step 5 still active:

```bash
aws --endpoint-url http://localhost:9000 s3 ls --recursive s3://warehouse/wsf/outputs/ckua_2nd/
aws --endpoint-url http://localhost:9000 s3 cp s3://warehouse/wsf/outputs/ckua_2nd/2026-04-01/<flow-run-id>/<attempt-id>/run.json - | head -30
```

Stage logs are also on the node while the cluster exists:
`docker exec kind-worker3 ls /data/wsf/runs/<flow-run-id>/<attempt-id>/logs`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `cannot execute: required file not found` | CRLF line endings - step 0.1. |
| `docker-credential-desktop.exe not found` | Step 0.2. |
| `namespaces "teehr-hub" not found` | Nothing deployed yet - step 4 (`garden deploy` creates it). |
| `garden: command not found` | Step 0 (install Garden). |
| `ModuleNotFoundError: importlib_metadata` from `prefect` | Use the full alias in step 6 (`--with importlib_metadata`); redefine the old alias. |
| Run stuck `Pending`, event `serviceaccount "prefect-job" not found` | `garden deploy prefect-job-sa --env local`, then re-trigger runs. |
| Run stuck `Pending`, event `persistentvolumeclaim "data-nfs" not found` | `garden deploy local-storage --env local`. |
| `ImagePullBackOff` | Images come from `localhost:5001`; `docker ps | grep kind-registry`; re-run the cluster script if missing. |
| `build` fails: `Operation not permitted` | `/data` is on a Windows drive - step 2; redo the bind mount after a restart. |
| `download` fails: 502 `wcc.sc.egov.usda.gov` | NRCS outage - wait (step 7). |
| `download` fails: 429 `api.waterdata.usgs.gov` | USGS rate limit - wait, run one model at a time, or add a USGS token (step 7). |
| `Unknown sites` / season ended | Use a January-July date and a site from that model's metadata. |
| `check-assets` checksum failure | Wrong S3 layout (no extra directory level); re-sync. Force a refetch by deleting `/data/wsf/assets/<solution>/<digest>` on the node. |
| Empty `wsf` S3 URI error | Step 3.2, then redeploy with `--force`. |
| Dashboard "Unable to connect" | UI patch in step 6. |
| No deployments listed | Re-run step 4 and watch `kubectl -n teehr-hub logs -f job/deploy-prefect-workflows` while it runs. |

## Teardown

```bash
kill %1 2>/dev/null                    # port-forwards started with &
kind delete cluster                    # removes cluster, cached assets and work dirs
docker rm -f kind-registry             # optional
```
