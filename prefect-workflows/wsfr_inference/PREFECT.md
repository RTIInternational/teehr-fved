# Rodeo Inference With Prefect

The three deployments execute models and archive their original CSV forecasts.
Warehouse loading, location mapping and new warehouse locations are deferred.
Outputs retain the original competition `site_id` values and KAF units. No
warehouse migrations or location crosswalks are required for execution.

## Runtime

`Dockerfile.prefect-wsf` derives from the existing TEEHR Prefect image. It uses
uv to install the locked dependencies from `pyproject.toml` and `uv.lock` into
the image's existing Python 3.12 system environment. Model subprocesses use the
same interpreter via `sys.executable`, with package-specific working
directories and module paths; the deployed image has no separate model venv.

The uv project caps xarray below 2026.9 to satisfy the existing TEEHR image; the
lock currently resolves xarray 2026.7.0 and rioxarray 0.23.0. The Docker install
is additive and keeps existing Prefect/TEEHR packages. Verify the built image and
run integration tests before deployment. The image build currently targets Linux
amd64; other architectures need explicit validation, including CPU PyTorch.

## Assets And S3 Configuration

Trained weights are not in Git. Obtain them from the model maintainers and stage
each model's assets in its own S3 prefix with the relative paths specified by
that package's `assets.sha256`. Do not upload the parent directory as another
level beneath that prefix.

Configure these Garden variables through the deployment target or a varfile:

```yaml
wsf:
  assetsS3Uri: s3://YOUR-BUCKET/wsf/assets
  outputS3Uri: s3://YOUR-BUCKET/wsf/outputs
```

The asset root must have `oshbocker_1st/`, `ckua_2nd/` and `rasyidstat_3rd/`
prefixes. For example, the ckua root contains `results/forecast/` immediately
beneath `wsf/assets/ckua_2nd/`. A flow's `assets_s3_uri` parameter overrides the
default and specifies the exact per-model asset prefix, not its parent.
The `output_s3_uri` parameter overrides the output root.

Defaults are blank so no existing bucket is assumed. The service account needs
read access to assets and write access to outputs. Remote runs reuse
`prefect-job` credentials; local runs inherit the existing local-S3 credentials
and endpoint. `WSF_S3_ENDPOINT_URL` can override the existing S3 endpoint for a
direct local process invocation. Boto3 uses bounded standard retries for S3.

Assets are downloaded into staging, checksum-verified, then renamed into
`/data/wsf/assets/<solution>/<manifest-digest>/`. Existing corrupt assets cause
a clear failure; remove that digest directory while the solution is stopped
to force a clean fetch. Working roots under
`/data/wsf/work/<source-digest>/<issue-date>/<solution>/` link to verified assets
and retain downloads and preprocessing for reruns of the same date/version.
Do not modify cached assets while inference is running.

## Third-Place Credentials

Strict mode requires Copernicus CDS credentials and acceptance of the ERA5-Land
and SEAS5 dataset licences. Add optional `cdsapi-url` and `cdsapi-key` entries to
the existing `prefect-workflow-secrets` Kubernetes Secret. The secret-loading
job provisions corresponding Prefect Secret blocks. Alternatively, provision
those blocks directly. Do not put keys in deployment parameters or Git.

For a direct local invocation, `CDSAPI_URL` and `CDSAPI_KEY`, or `~/.cdsapirc`,
are supported. The first two solutions do not require CDS credentials.

## Build And Deploy

Run the normal Garden deployment for your configured local or remote target:

```bash
garden deploy prefect-workflow-deploy --env remote
```

The action builds `teehr-prefect-image`, then `wsf-prefect-image`, and passes
the resolved WSF image to the deployment-registration job. The existing base
Dockerfile and other workflows' runtime images are unchanged. The worker's
existing `data-nfs` PVC supplies `/data`; verify UID 1000 can write there.

The registered deployments are:

- `wsf-inference/wsf-inference-oshbocker-1st`
- `wsf-inference/wsf-inference-ckua-2nd`
- `wsf-inference/wsf-inference-rasyidstat-3rd`

Trigger a manual run with an explicit January-July issue date:

```bash
prefect deployment run wsf-inference/wsf-inference-ckua-2nd \
  --param issue_date=2026-03-01
```

`sites` optionally limits inference to original competition site IDs. Site and
season eligibility come from each model's bundled metadata, not warehouse
locations. The default runs all eligible sites (Detroit is excluded after its
June season end). Output must contain exactly one valid row per eligible
requested site, with finite, nonnegative, ordered quantiles and a model version.

`strict_ensemble` defaults to true. Third-place inputs such as ERA5/SEAS5 arrive
after the issue date; scheduled same-day runs can therefore fail until required
inputs are available. This is intentional: full-ensemble mode does not silently
publish partial forecasts or move the issue date. An explicit manual override
`strict_ensemble=false` permits missing ensemble variants, but never invalid
output or missing requested sites. The CLI's `--allow-partial` is never used.

## Scheduling

All three schedules are initially inactive:

```yaml
cron: "0 8 1,8,15,22 1-7 *"
timezone: UTC
active: false
```

This gives 28 annual issue dates at 08:00 UTC. Enable schedules only after
assets, credentials, permissions and representative forecasts are validated.
Scheduled runs derive their issue date from Prefect's expected scheduled start,
not the actual worker start or current date. Explicit issue dates support
manual runs/backfills. Each deployment permits one concurrent run; a persistent
per-solution file lock additionally protects shared working files. The shared
filesystem must support advisory locks (verify on the target PVC).

## Outputs And Failures

Each attempt has an independent archive:

```text
<output-root>/<solution>/<issue-date>/<flow-run-id>/<attempt-id>/
  forecast.csv
  logs/<stage>.log
  run.json
```

The CSV is unmodified model output. `run.json` records status, units, model
versions, issue date, timestamps, requested sites and code/environment/asset
digests; it is uploaded last. Failed stages archive available diagnostics with
`status=failed` and re-raise the failure. A CSV left by an unsuccessful process
is never accepted as a successful forecast. If archival fails, files remain in
`/data/wsf/runs/<flow-run-id>/<attempt-id>/` and the successful path fails.
Do not treat a CSV without a successful completion record as published output.

Stage output is streamed to Prefect and archived with environment-secret
redaction. Native model log files remain in the working root. Download timeout
defaults to two hours, other stages to 30 minutes, and the flow to three hours;
the Kubernetes deadline/watch window is longer. Timeout cleanup terminates the
model process group. Model scientific failures are not automatically retried;
inspect diagnostics before triggering a rerun.

## Firewall Probe Handoff

`check_data_sources.py` is independent of the model packages, trained assets and
the `wsf_py313` environment. Give the backend team this script and a Python
installation with `requests` available. Run it from any directory:

```bash
python -m pip install requests
python check_data_sources.py
```

It probes all unique runtime data-source endpoints used by the three models,
follows HTTP redirects, and prints an exit code of 1 if any request or basic
response-shape check fails. `--timeout` changes the per-request timeout in
seconds. An HTTP response with a non-2xx status still means the host was
reached; inspect the reported status separately from firewall connectivity.
The CDS probes check public catalogues only. They do not test CDS credentials,
dataset entitlements or file-download redirect hosts.

The probe makes small read-only requests. NetCDF probes request a byte range to
avoid downloading large products. Endpoint response shape and current data
availability can change independently of firewall access.

## Local Verification

The checks below progress from quick offline validation to a live forecast.
They use the same locked Python 3.12 dependency set as the WSF image.

### 1. Sync And Run Offline Model Tests

```bash
cd prefect-workflows/wsfr_inference
uv sync --locked --python 3.12
for model in ckua_2nd oshbocker_1st rasyidstat_3rd; do
  (
    cd "$model"
    PYTHONPATH="$PWD" uv run --project .. python -m pytest tests/test_offline.py -q
  ) || exit $?
done
```

These are offline tests and do not need trained assets, network access, Prefect,
S3, or CDS credentials. They exercise each model's checksums, patches, data
validation and output schema. Run the standalone source probes separately when
you want to check live upstream endpoints:

```bash
python3 prefect-workflows/wsfr_inference/check_data_sources.py
```

### 2. Build And Smoke-Test The WSF Image

The WSF image inherits Prefect/TEEHR from the base image. Build or pull that
base image first, then build the WSF image from the `prefect-workflows`
directory. Replace `teehr-prefect:latest` with the actual base image reference
if Garden tagged it differently:

```bash
cd prefect-workflows
docker build \
  --build-arg PREFECT_BASE_IMAGE=teehr-prefect:latest \
  --file Dockerfile.prefect-wsf \
  --tag teehr-prefect-wsf:local .
```

Run the workflow tests inside that image; this checks the installed Prefect,
system Python, deployment YAML and model code together:

```bash
docker run --rm --entrypoint python teehr-prefect-wsf:local \
  -m pytest /teehr/workflows/tests/wsf_forecasts_test.py -q
```

Check that each model CLI imports in the same image interpreter:

```bash
for pair in "ckua_2nd ckua_infer" "oshbocker_1st oshbocker_infer" "rasyidstat_3rd rasyidstat_infer"; do
  set -- $pair
  docker run --rm --entrypoint python \
    --workdir "/teehr/wsfr_inference/$1" \
    --env "PYTHONPATH=/teehr/wsfr_inference/$1" \
    teehr-prefect-wsf:local -m "$2" --help
done
```

### 3. Run A Live Flow Locally

A live forecast additionally needs internet access to the data sources, a valid
January-July issue date, the model's trained assets in the configured S3 prefix,
S3 read/write credentials, and enough local disk for the cache. For the 3rd
model's strict full ensemble, also provide licensed CDS credentials. Do not put
credentials in the command line or commit them; use your normal local AWS
credential provider and local environment or `~/.cdsapirc` for CDS.

Create a writable cache directory and set non-secret S3 locations in the shell:

```bash
export WSF_LOCAL_CACHE="${TMPDIR:-/tmp}/wsf-cache"
mkdir -p "$WSF_LOCAL_CACHE"
export WSF_ASSETS_S3_URI=s3://YOUR-BUCKET/wsf/assets
export WSF_OUTPUT_S3_URI=s3://YOUR-BUCKET/wsf/outputs
```

Invoke the Prefect flow directly in the container. This runs the actual flow and
subprocess pipeline without deploying it to Kubernetes. The required parameters
below use a supported issue date and one site to keep the first check smaller:

```bash
docker run --rm \
  --mount "type=bind,src=$WSF_LOCAL_CACHE,dst=/data/wsf" \
  --mount "type=bind,src=$HOME/.aws,dst=/home/prefect/.aws,readonly" \
  --env WSF_ASSETS_S3_URI \
  --env WSF_OUTPUT_S3_URI \
  --env AWS_REGION \
  --env AWS_PROFILE \
  --env CDSAPI_URL \
  --env CDSAPI_KEY \
  --entrypoint python \
  teehr-prefect-wsf:local -c '
from workflows.models.wsf_forecasts import run_wsf_inference
run_wsf_inference(
    solution="ckua_2nd",
    issue_date="2026-03-01",
    sites=["american_river_folsom_lake"],
    cache_dir="/data/wsf",
)
'
```

The model's season/site metadata is used; warehouse locations and TEEHR tables
are not involved. Use `solution="oshbocker_1st"` or
`solution="rasyidstat_3rd"` to test the other models. The 3rd model defaults to
`strict_ensemble=True` and needs ERA5-Land/SEAS5.1 to be available; set
`strict_ensemble=False` only when intentionally testing partial-ensemble mode.
Alternatively run `python -m <model-package> run --issue-date YYYY-MM-DD` from
that package directory inside the image to test the model CLI without Prefect.

### 4. Test A Local Prefect Deployment

To test deployment registration and a worker run, start the local Garden/KIND
stack and deploy with the local environment. Configure local S3 asset/output
variables and credentials first:

```bash
garden deploy prefect-workflow-deploy --env local
prefect deployment run wsf-inference/wsf-inference-ckua-2nd \
  --param issue_date=2026-03-01 \
  --param sites='["american_river_folsom_lake"]'
```

Schedules are intentionally inactive. Trigger runs manually during testing.

The regression tests are opt-in and perform real downloads; they also need
trained weights. Offline tests and mocked workflow tests do not prove upstream
availability, S3 permissions, a successful full forecast, or a Docker/Kubernetes
deployment. The Docker example mounts the local AWS profile directory; omit or
replace that mount if your AWS credential provider is configured differently.
`$WSF_LOCAL_CACHE` is outside the repository and can be removed after the run
completes.