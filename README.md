# teehr-fved
Repository for the U.S. Bureau of Reclamation's Forecast Visualization and Evaluation Dashboard

## Water Supply Forecast Inference

The three Rodeo inference solutions run through independent Prefect deployments
using one shared Python 3.13 model environment. Forecast CSVs and run provenance
are archived to S3; warehouse loading and location setup are deferred.
See [the execution runbook](prefect-workflows/wsfr_inference/PREFECT.md) for asset
staging, configuration, credentials, manual runs and initially inactive schedules.
