# teehr-fved
Repository for the U.S. Bureau of Reclamation's Forecast Visualization and Evaluation Dashboard

## Water Supply Forecast Inference

The three Rodeo inference solutions run through independent Prefect deployments
using one shared, isolated Python model environment. Forecast CSVs and run provenance
are archived to S3; warehouse loading and location setup are deferred.
See [the local KinD runbook](prefect-workflows/wsfr_inference/LOCAL_KIND.md) for asset
staging, configuration, credentials and manual runs. Schedules are initially inactive.
