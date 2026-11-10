Upstream: 3rd place (rasyidstat) Water Supply Forecast Rodeo, Final Prize Stage, `overall` phase solution
(9 LightGBM variants, `ens_all` ensemble trained on 1981-2023).

`core/src` and `core/configs` are byte-identical to `vendor/rasyidstat_lgbm_3rd/{src,configs}` of this repository (itself an
unmodified copy of the competition repository's `overall/3rd place`; see `../../VENDORED.md`). `static/meta` and `static/raw`
are the competition's public metadata and the solution's own site/station metadata (`data/meta`, `data/raw` of the same folder).
The trained models (`assets/models/<variant>/`, 172 MB) are the QC wrapper's overall-config training run (trained through 2023); they are not in git, see `assets.sha256`.

`core.sha256` pins every file under `core/`; `python -m rasyidstat_infer check-assets` and the build fail if any file differs.
