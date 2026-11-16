# Run The `wsf-inference` Prefect Workflow Locally (KinD)

End-to-end runbook: stand up the local KinD + Garden stack, stage model assets
in the in-cluster S3, and execute all three deployments
(`wsf-inference-oshbocker-1st`, `-ckua-2nd`, `-rasyidstat-3rd`) as real Prefect
flow runs on a local Kubernetes worker. Complements `PREFECT.md` (reference) and
`teehr-cloud-core/README.md` (platform).

All commands are run from the repo root (`teehr-fved/`) unless stated.
Only the Prefect-related services are deployed (no Keycloak/JupyterHub/Trino),
which keeps RAM use manageable.

## 0. What you need before starting

| Need | Notes |
|---|---|
| x86_64 Linux/WSL2 | `Dockerfile.prefect-wsf` only builds on amd64. |
| Docker | Give it >= 12 GB RAM and ~40 GB disk (images + 3rd-model downloads). |
| `kind`, `kubectl`, `uv` | Already installed on this machine. |
| `garden` 0.13.x | **Not installed yet** - see step 1. |
| Trained model assets | NOT in git. Get the three asset trees from the model maintainers (step 5). |
| Copernicus CDS key | Only for `rasyidstat_3rd` strict mode. Accept ERA5-Land and SEAS5 licences at cds.climate.copernicus.eu. |
| Internet access | Models download live data (SNOTEL, CDEC, ACIS, ERA5/SEAS5, ...). Optionally run `python prefect-workflows/wsfr_inference/check_data_sources.py` first. |

Keep the repo on the WSL ext4 filesystem if you can (e.g. `~/repos/teehr-fved`);
bind mounts from `/mnt/c` are slow and have permission quirks (step 3 covers it).

## 1. Install Garden

```bash
brew install garden-io/garden/garden-cli      # or follow docs.garden.io
garden version                                 # known-good: 0.13.54
```

## 2. Hostnames

Add to `/etc/hosts` (WSL; also the Windows hosts file if you use a Windows browser):

```text
127.0.0.1  prefect.teehr.local.app.garden s3.teehr.local.app.garden
```

(Not strictly required - steps below use `kubectl port-forward` - but handy.)

## 3. Create the KinD cluster

```bash
git submodule update --init teehr-cloud-core
./teehr-cloud-core/kind/create_kind_cluster.sh
kubectl config current-context                 # must be: kind-kind
kubectl get nodes                              # 1 control-plane + 3 workers Ready
```

Notes:
- Ports 80/443 on the host must be free.
- The script mounts `teehr-cloud-core/data` into every node as `/data`; the Prefect
  job pods (UID 1000) write `/data/wsf` there. Make it writable:
  ```bash
  chmod -R a+rwx teehr-cloud-core/data
  ```
- Contour (ingress) is installed by the script; wait until
  `kubectl -n projectcontour get pods` shows everything Running.

## 4. Configure secrets and WSF variables

### 4a. CDS credentials (3rd model only)

Create the git-ignored file `teehr-cloud-core/secrets/secrets.local.private.yaml`
containing only the keys you want to add/override (it layers over
`secrets.local.yaml`):

```yaml
secrets:
  prefect-workflow-secrets:
    data:
      api-usgs-pat: CHANGE_ME_API_USGS_PAT
      crmms-esp-password-format: CHANGE_ME_CRMMS_ESP_PASSWORD_FORMAT
      m3works-aws-access-key-id: CHANGE_ME_M3WORKS_AWS_ACCESS_KEY_ID
      m3works-aws-secret-access-key: CHANGE_ME_M3WORKS_AWS_SECRET_ACCESS_KEY
      cu-swe-aws-access-key-id: CHANGE_ME_CU_SWE_AWS_ACCESS_KEY_ID
      cu-swe-aws-secret-access-key: CHANGE_ME_CU_SWE_AWS_SECRET_ACCESS_KEY
      cdsapi-url: https://cds.climate.copernicus.eu/api
      cdsapi-key: <YOUR-CDS-PERSONAL-ACCESS-TOKEN>
```

(All keys of the block are repeated so that nothing is lost if the varfile merge
replaces the whole `prefect-workflow-secrets` entry.) Never commit this file.
Skip this step if you only run models 1 and 2.

### 4b. S3 locations for assets and outputs

The in-cluster S3 (RustFS, endpoint `http://local-s3:9000`, credentials
`localadmin` / `localadmin123`) is created with a single bucket, `warehouse`.
Use prefixes in that bucket. In `project.garden.yml`, set the top-level
`wsf` variables (local edit; do not commit):

```yaml
variables:
  wsf:
    assetsS3Uri: s3://warehouse/wsf/assets
    outputS3Uri: s3://warehouse/wsf/outputs
```

The flow reads the S3 endpoint from `REMOTE_CATALOG_S3_ENDPOINT`, which the local
environment already injects together with the S3 credentials.

## 5. Stage the model assets in local S3

Required layout (each model's files at the root of its own prefix, with the
relative paths listed in that model's `assets.sha256`):

```text
s3://warehouse/wsf/assets/oshbocker_1st/models/*.txt, feature_parameters/*.csv
s3://warehouse/wsf/assets/ckua_2nd/results/forecast/*.pth, *.pkl
s3://warehouse/wsf/assets/rasyidstat_3rd/...   (see rasyidstat_3rd/assets.sha256)
```

Get the files from the maintainers into e.g. `~/wsf-assets/<model>/...` and
verify before upload (prints nothing but `OK` lines on success):

```bash
for m in oshbocker_1st ckua_2nd rasyidstat_3rd; do
  (cd ~/wsf-assets/$m && sha256sum -c --quiet \
     /mnt/c/workspace/repos/teehr-fved/prefect-workflows/wsfr_inference/$m/assets.sha256 && echo "$m OK")
done
```

The S3 service exists only after the deploy in step 6a. Once it is up:

```bash
kubectl -n teehr-hub port-forward svc/local-s3 9000:9000 &      # keep running
export AWS_ACCESS_KEY_ID=localadmin AWS_SECRET_ACCESS_KEY=localadmin123 AWS_DEFAULT_REGION=us-east-1
# any S3 CLI works; with aws-cli v2:
for m in oshbocker_1st ckua_2nd rasyidstat_3rd; do
  aws --endpoint-url http://localhost:9000 s3 sync ~/wsf-assets/$m s3://warehouse/wsf/assets/$m
done
aws --endpoint-url http://localhost:9000 s3 ls s3://warehouse/wsf/assets/ckua_2nd/results/forecast/ | head
```

(No aws-cli? `uvx --from awscli aws ...` works too.) The flow re-verifies
checksums when it downloads, so a wrong layout fails clearly in `check-assets`.

## 6. Deploy

### 6a. Deploy the platform pieces and the workflows

```bash
garden deploy prefect-workflow-deploy --env local
```

Garden builds `teehr-prefect-image` -> `wsf-prefect-image` (+ spark executor
image) and deploys Prefect server, worker, secrets, the work-pool job template
and the registration job. The first run takes a long time (image builds).
`local-s3` is pulled in via the secrets/storage dependencies; if
`kubectl -n teehr-hub get svc local-s3` is missing afterwards, run
`garden deploy local-s3-deploy create-local-s3-bucket --env local` and re-run
the command above.

If the S3 upload (step 5) was not possible earlier, do it now, **before**
triggering runs.

### 6b. Verify

```bash
kubectl -n teehr-hub get pods                       # prefect-server, prefect-worker Running
kubectl -n teehr-hub logs job/deploy-prefect-workflows | tail -30
kubectl -n teehr-hub get secret prefect-workflow-secrets -o jsonpath='{.data}' | grep -c cdsapi   # 3rd model only
```

The registration job (ttl 60s) is deleted quickly; if the logs are gone, check
deployments via the CLI in step 7. If you changed `wsf.*` or secrets, redeploy:
`garden deploy prefect-workflow-deploy --env local --force`.

## 7. Execute the workflow

Prefect's UI proxy needs Keycloak, which we didn't deploy; talk to the server
API directly.

```bash
kubectl -n teehr-hub port-forward svc/prefect-server 4200:4200 &   # keep running
uvx --from "prefect==3.4.24" prefect --help >/dev/null             # warms the CLI
export PREFECT_API_URL=http://localhost:4200/api
alias prefect='uvx --from prefect==3.4.24 prefect'

prefect deployment ls | grep wsf-inference          # expect the 3 deployments
prefect work-pool ls                                # kubernetes-pool
```

Open the dashboard at http://localhost:4200 (the server's own UI, no login).

Run each model. Use an issue date between January and July and, for the first
pass, a single site to keep it small:

```bash
prefect deployment run wsf-inference/wsf-inference-ckua-2nd \
  --param issue_date=2026-03-01 --param sites='["american_river_folsom_lake"]'

prefect deployment run wsf-inference/wsf-inference-oshbocker-1st \
  --param issue_date=2026-03-01 --param sites='["american_river_folsom_lake"]'

prefect deployment run wsf-inference/wsf-inference-rasyidstat-3rd \
  --param issue_date=2026-03-01 --param sites='["american_river_folsom_lake"]'
```

Notes:
- Site IDs are the competition IDs in each package's `static/metadata.csv`
  (omit `--param sites` to run all eligible sites - much slower). If a model
  rejects the site, pick another from its metadata.
- Run them sequentially; they share the node and each downloads data.
- `rasyidstat_3rd` is strict by default and needs ERA5-Land/SEAS5 for the
  issue date, which are published with a delay. For a past date this is
  normally fine; for an experiment add `--param strict_ensemble=false`
  (partial ensemble allowed). Without CDS credentials strict mode fails
  immediately with "requires CDSAPI_URL/CDSAPI_KEY".
- The first run of each model downloads assets from S3 into
  `/data/wsf/assets/...` (host: `teehr-cloud-core/data/wsf/`) and caches them.
  Downloads/preprocessing can take 10+ minutes.

Monitor:

```bash
prefect flow-run ls --limit 5
kubectl -n teehr-hub get pods -w                     # a job pod per flow run (on kind-worker3)
kubectl -n teehr-hub logs -f <job-pod-name>          # live stage logs
```

Optionally: `prefect deployment run ... --watch` to block until done.

## 8. Check the results

Each run archives to
`s3://warehouse/wsf/outputs/<solution>/<issue-date>/<flow-run-id>/<attempt-id>/`
(`forecast.csv`, `run.json`, `logs/<stage>.log`). A run counts as published only
when `run.json` has `"status": "succeeded"`.

```bash
aws --endpoint-url http://localhost:9000 s3 ls --recursive s3://warehouse/wsf/outputs/ckua_2nd/
aws --endpoint-url http://localhost:9000 s3 cp \
  s3://warehouse/wsf/outputs/ckua_2nd/2026-03-01/<flow-run-id>/<attempt-id>/run.json - | head -30
```

(AWS credentials env vars from step 5 must still be exported.) On failure the
same prefix holds `status: failed` plus stage logs.

## 9. Iterate / troubleshoot

| Symptom | Fix |
|---|---|
| `garden: command not found` | Step 1. |
| Job pod `Pending` | Node selector/taint: `kubectl get nodes --show-labels`; `kind-worker3` must have `teehr-hub/nodegroup-name=spark-r5-4xlarge` (set by the create script). Check RAM. |
| `ImagePullBackOff` | Images come from `localhost:5001` (kind registry). `docker ps | grep kind-registry`; rerun the create script if missing. |
| Permission denied on `/data/wsf` | `chmod -R a+rwx teehr-cloud-core/data`. |
| `Unknown sites` / season ended | Use a January-July date and a site from that model's metadata. |
| Asset checksum/`check-assets` failure | S3 layout wrong (don't add an extra directory level) - re-sync; to force refetch delete `teehr-cloud-core/data/wsf/assets/<solution>/<digest>`. |
| Empty `wsf` S3 URI error | Step 4b, then redeploy with `--force`. |
| Code change in `workflows/` or `wsfr_inference/` | Re-run `garden deploy prefect-workflow-deploy --env local` (rebuilds image and re-registers). |
| No `prefect` deployments listed | Re-run the deploy; check `kubectl -n teehr-hub logs job/deploy-prefect-workflows`. |

Faster loops without Kubernetes: `PREFECT.md` section "Run A Live Flow Locally"
runs the same flow function inside the built image with `docker run`.

## 10. Teardown

```bash
kill %1 %2 2>/dev/null                 # port-forwards
kind delete cluster                    # removes the cluster
docker rm -f kind-registry             # optional
rm -rf teehr-cloud-core/data/wsf       # cached assets/work dirs
```
