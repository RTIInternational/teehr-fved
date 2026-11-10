# Rodeo Inference With Prefect

The three deployments execute models and archive their original CSV forecasts.
Warehouse loading, location mapping and new warehouse locations are deferred.
Outputs retain the original competition `site_id` values and KAF units. No
warehouse migrations or location crosswalks are required for execution.

## Runtime

`Dockerfile.prefect-wsf` derives from the existing TEEHR Prefect image. Its one
shared Python 3.13 environment, `wsf_py313`, is built from
`environment-py313.yml`. Micromamba is a lightweight build-time installer for
this standard conda environment specification; it is not required at runtime.
All three models run through `/opt/conda/envs/wsf_py313/bin/python` in separate
processes, with package-specific working directories and module paths.

Prefect and its orchestration dependencies stay in the base Python 3.12
environment. In particular, do not install the model environment's xarray into
the orchestration environment: the base image has a different xarray constraint.
The initial image build supports Linux amd64. Other architectures need explicit
validation of all pinned packages, including CPU PyTorch.

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

## Local Verification

Create the shared model environment using any compatible conda/mamba installer.
Run the source offline tests separately from each solution directory:

```bash
PYTHONPATH=$PWD /path/to/wsf_py313/bin/python -m pytest tests/test_offline.py
```

Run orchestration tests from the repository root in an environment containing
Prefect 3.4.24, pytest, pandas, numpy, boto3, PyYAML and croniter:

```bash
python -m pytest prefect-workflows/workflows/tests/wsf_forecasts_test.py -q
```

Live endpoint/regression tests are opt-in and require network access, weights
and relevant credentials. Offline checks and mocked orchestration tests do not
prove a Docker build, cluster deployment or live forecast succeeds.