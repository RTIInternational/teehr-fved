"""Arguments and defaults of the gridded Prefect flows: teehr-icechunk's inputs with this deployment's defaults and sources."""
import os
from typing import Optional

from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema
from teehr_icechunk import models as ic_models
from teehr_icechunk.models import OVERVIEW_CHUNK_SIZE, ParserType  # noqa: F401 (used by the flows and tests)

from workflows.models.gridded_sources import GriddedSourceType

ICECHUNK_BUCKET = os.getenv("ICECHUNK_BUCKET")
ICECHUNK_PREFIX = os.getenv("ICECHUNK_PREFIX")


class _Defaults(BaseModel):
    """This deployment's defaults for every gridded input; listed first in each model so they win."""

    dest_bucket: str = Field(
        default=ICECHUNK_BUCKET,
        description="S3 bucket name for the destination IceChunk repository (e.g., 'ciroh-rti-public-data')"
    )
    base_prefix: str = Field(
        default=ICECHUNK_PREFIX,
        description="Base path prefix within the bucket for the IceChunk repository"
    )
    x_dim: str = Field(
        default="lon",
        description="Name of the x spatial dimension in the source data"
    )
    y_dim: str = Field(
        default="lat",
        description="Name of the y spatial dimension in the source data"
    )


class BaseGriddedDataInput(_Defaults, ic_models.BaseGriddedDataInput):
    """Base model for gridded data analysis parameters."""


class BuildOverviewsDataInput(_Defaults, ic_models.BuildOverviewsDataInput):
    """Input parameters for the build_overviews Prefect flow."""

    source: Optional[GriddedSourceType] = Field(
        default=None,
        description=(
            "The gridded data source, e.g. {'type': 'ua-swann-4km'}; sets configuration_name and the overview "
            "packing. Or set configuration_name alone for a repo without a source here"
        )
    )


# Also a BuildOverviewsDataInput of this deployment, so the ingest flow can pass its args to the overview flow
class IngestGriddedDataInput(BuildOverviewsDataInput, ic_models.IngestGriddedDataInput):
    """Input parameters for the ingest_gridded_data Prefect flow.

    ``source`` selects the data source by its ``type``. Dataset fields (dims, kwargs, ...)
    default to UA SWANN's values; deployments for other sources override them. The
    repository name (``configuration_name``), ``variable_names`` and ``append_dim`` are derived
    from the source and hidden from the flow's parameters.
    """

    source: GriddedSourceType = Field(
        ...,
        description="The gridded data source, e.g. {'type': 'ua-swann-4km'}"
    )
    # Hidden again here: pydantic takes inherited fields from the first base, which shows them, and the
    # Prefect UI would send their defaults
    configuration_name: SkipJsonSchema[Optional[str]] = None
    append_dim: SkipJsonSchema[Optional[str]] = None
