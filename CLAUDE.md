# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

FVED (Forecast Visualization and Evaluation Dashboard) for the U.S. Bureau of Reclamation. It is a client deployment built on **TEEHR Cloud Core**, which lives in the `teehr-cloud-core/` git submodule. Core provides the platform: JupyterHub, Prefect server, Keycloak, Polaris (Iceberg REST catalog), Spark, Trino, the FastAPI `api`, `xpublish-api` and local S3. This repo adds the FVED-specific parts:

- `frontend/`: React 19 + TypeScript + Vite dashboards (MapLibre, Plotly, TanStack Query).
- `prefect-workflows/`: Prefect 3 flows for ingest, metrics and maintenance, using the `teehr` Python library.
- `warehouse_migrations/`: Iceberg schema migrations for FVED's TEEHR warehouse.
- `warehouse/`: notebooks for setting up, loading and maintaining the warehouse (run in JupyterHub).
- `ingress/`, `cert-manager/`, `jupyterhub-profiles/`: FVED-specific garden actions alongside core's.

The sibling repo **teehr-hub** is the other client of teehr-cloud-core. Several flows and frontend pieces exist in both repos and are expected to stay in step.

## Working guidelines

- **Follow existing patterns.** Match the surrounding code's conventions, style and architecture. Don't introduce new notation, styles, abstractions or architecture unless necessary, and ask before doing so.
- **Keep comments and docstrings minimal.** Keep only what's important, in clear, concise language the whole team can follow.
- **Remove dangling code.** Before finishing, delete leftovers from earlier iterations: unused functions, params, imports, branches and stale comments.
- **Follow best practices and keep it DRY.** Reuse existing helpers, here, in teehr-cloud-core or in teehr, instead of duplicating logic. Keep the overall architecture in mind and how a change fits with the rest of the system, including the teehr-hub copies.
- **Design for scale.** Development and testing happen on a laptop with small data, but deployed runs get much more compute and much larger datasets. Bound memory (batch, stream, avoid loading everything at once) and consider how a change scales before choosing an approach.

## Deployment (Garden + Kubernetes)

`project.garden.yml` at the root drives everything. Garden discovers every `garden.yaml` in this repo **and** in `teehr-cloud-core/`, so core and FVED actions deploy together.

- There are two environments. `local` uses a kind cluster (context `kind-kind`, registry `localhost:5001`) and is the default. `remote` is the FVED EKS cluster.
- `devTeehrVersion` in `project.garden.yml` sets the **teehr git SHA** baked into the Prefect image (`Dockerfile.prefect-teehr` pip-installs `git+https://github.com/RTIInternational/teehr.git@<sha>`). To pick up a teehr change, push it and bump this SHA in both environments.
- Local setup:
  1. Create the cluster with `teehr-cloud-core/kind/create_kind_cluster.sh`.
  2. Provide secrets in `teehr-cloud-core/secrets/secrets.local.private.yaml` (example alongside it).
  3. Run `garden deploy`. Use `garden deploy <action-name>` for a single action.
- Hosts are `*.teehr.local.app.garden` and use self-signed certs. Accept the cert for `api.` and `xpublish-api.` in the browser first, or the dashboards fail with what looks like a CORS error.
- Remote deploys run from GitHub Actions in a separate repo, not from this one. Values the platform must provide are documented in `teehr-cloud-core/docs/platform-app-deployment-contract.md`.

## Prefect workflows

- **How flows reach Prefect.** The `teehr-prefect-image` build copies `workflows/`, `prefect-local.yaml` and `prefect-remote.yaml` into `/teehr`. The `prefect-workflow-deploy` job then runs `prefect deploy --all --prefect-file prefect-{local,remote}.yaml`. A flow only has a deployment if it has an entry in those YAML files; keep the local and remote files in step.
- **Deployment timeouts.** A garden timeout on `deploy.prefect-workflow-deploy` is usually a bad `prefect-*.yaml`, such as an undefined YAML alias. The real error is in the `deploy-prefect-workflows` pod log, which only lives for 60s after the job finishes.
- **Job environment.** Flow runs execute as Kubernetes jobs. Their env comes from `work_pool_job_variables_base` in the prefect YAML: Polaris catalog settings, `ICECHUNK_BUCKET`/`ICECHUNK_PREFIX`, `PMTILES_*`, and `ZARR_ASYNC__CONCURRENCY`. Spark executors use a separate image and `executor-pod-template.yaml`.
- **Import paths.** Code imports `workflows.*` (from `prefect-workflows/`) and also bare `utils.*` and sibling modules (from `workflows/ingests/`), mirroring how Prefect sets `sys.path` from the entrypoint. `workflows/tests/conftest.py` reproduces this for pytest.
- **Layout.**
  - `workflows/ingests/` holds the flows plus `utils/` (`grid_utils.py` for Icechunk/zarr/virtual references, `time_grid.py` for the per-step status time axis).
  - `workflows/models/` holds the pydantic input models. Every flow takes a single `args: <Model>` parameter.
  - `workflows/utils/common_utils.py` provides `initialize_evaluation`, which creates the teehr `Evaluation` and Spark session.
- **Two storage systems.**
  - Tabular TEEHR data (timeseries, locations, domain tables) lives in the **Iceberg warehouse** via teehr/Spark. Writes go through `ev._write.to_warehouse(...)` with `append`/`upsert` MERGE semantics keyed on `uniqueness_fields`, and this path skips teehr's validation.
  - Gridded data (UA SWANN, iSnobal, NWM forcing) lives in **Icechunk repos** on S3, one repo per `configuration_name` under `ICECHUNK_PREFIX`.
- **Icechunk repo layout.** A repo has `/references` (virtual chunks), `/raw_data` (materialized) and `/pyramids` (multiscale levels for map tiles). The root attr `data_group` tells readers which data group to use; read it with `grid_utils.read_data_group`.
- **Image has no dask.** `xr.open_zarr` returns lazily indexed arrays, and read concurrency comes from zarr async (`ZARR_ASYNC__CONCURRENCY`) or teehr's `teehr.utils.concurrency.run_concurrent_map`.

### Tests

There is no CI for Python; tests run locally in an environment that has teehr and pyspark installed (tests `importorskip` them):

```bash
cd prefect-workflows
pytest workflows/tests                                         # all
pytest workflows/tests/mean_areal_values_test.py::test_window  # single test
```

`distributed_rw_auth_test.py` is a flow run against a live cluster, and conftest excludes it from collection.

## Warehouse migrations

`warehouse_migrations/NNNN/*.sql` are applied in order by teehr's `evolve_catalog_schema`, run from `warehouse/remote/01_initialization/01_apply_migrations.ipynb`. They are not applied by a deploy. Add a new numbered folder; never edit an applied migration. Migrations cover the core teehr tables (`0001`–`0008` mirror teehr's own `src/teehr/migrations`). Non-core tables, such as metrics, dashboard summaries and `grid_pixel_coverage_weights`, are created by the flow that owns them, using `create_or_replace` when `table_exists` is false.

## Frontend

```bash
cd frontend
npm ci
npm run dev            # Vite dev server on :8080
npm run build          # tsc -b && vite build
npm run lint           # oxlint, --max-warnings 0
npm run format:check   # oxfmt; format:fix to apply
```

CI (`.github/workflows/frontend-ci.yaml`) runs `format:check`, `lint` and `build` on PRs that touch `frontend/`. Set API and auth endpoints with `VITE_*` variables in `frontend/.env` (see `frontend/README.md`). Code is organized by feature under `src/features/` (`forecast`, `gridded`, `data_management`, `auth`). Reusable pieces go in `src/shared/`, and API calls go in `src/services/`. Reuse existing shared components and patterns before adding new ones.

## teehr-cloud-core submodule

Changes to core services (`api`, `xpublish-api`, auth, Spark, etc.) belong in the `teehr-cloud-core` repo. Commit them there, then update the submodule pointer here (the `chore: update submodule commit` commits). The core `api` uses ruff and pytest, configured in `teehr-cloud-core/api/pyproject.toml`.
