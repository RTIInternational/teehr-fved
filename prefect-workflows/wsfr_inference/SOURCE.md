# Inference Import Provenance

Imported from the local working tree of
`fved-water-supply-rodeo-forecasts/inference` at commit
`754b95c347bcb626f034a7860e69263ceae26b7c` on 2026-11-10.

The import includes the source working-tree changes to
`ckua_2nd/ckua_infer/solution.py` and `ckua_2nd/CHANGES.md`: suppression of
scikit-learn's `InconsistentVersionWarning` for the older serialized scalers.
No other source working-tree files outside `inference` were imported.

Each solution retains its own `SOURCE.md`, pristine `core/`, ordered patches,
checksum manifests, static inputs and tests. Consult those source documents
for attribution and licensing. Trained assets are not included in this repository;
their distribution and use must follow the upstream asset terms.

`pyproject.toml` and `uv.lock` define the shared Python 3.12 dependency set. The
individual model environment YAML files and the experimental
`environment-py313.yml` were removed in the transition to uv. The deployed WSF
image installs the locked requirements into the existing Prefect/TEEHR Python
interpreter; local development uses `uv sync --locked`.