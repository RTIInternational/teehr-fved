"""Temporary: validate pixel coverage weights and mean areal values against independent calculations.

Checks the warehouse rows, compares weights x geodesic cell area with each polygon's geodesic area
(pyproj), and recomputes sampled basin-days from the raw grid with exactextract and geodesic cell
areas, applying the coverage threshold by hand. The run fails if any check fails.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import pyspark.sql.functions as F
import rioxarray  # noqa: F401
import xarray as xr
from exactextract import exact_extract
from prefect import flow, get_run_logger
from pydantic import Field
from pyproj import CRS
from shapely.geometry import box

from utils import grid_utils as gu
from workflows.utils.common_utils import initialize_evaluation
from workflows.models.mean_areal_inputs import MeanArealValuesInput
from mean_areal_values import _written_steps
from pixel_coverage_weights import WEIGHTS_TABLE_NAME, get_readonly_repo_store


class ValidateMeanArealValuesInput(MeanArealValuesInput):
    """Mean areal values inputs plus the validation sample."""

    n_basins: int = Field(20, description="Basins to recompute; half with the fewest values, half random")
    n_days: int = Field(30, description="Days recomputed per basin, plus up to 5 dropped days")
    seed: int = Field(0, description="Random seed for the sample")
    rel_tol: float = Field(2e-3, description="Relative tolerance; the flow uses cos(latitude), not geodesic areas")
    abs_tol: float = Field(1e-3, description="Absolute tolerance for values near zero, in the variable's units")


@flow(
    name="validate-mean-areal-values",
    description="Temporary: validate pixel coverage weights and mean areal values against independent calculations."
)
def validate_mean_areal_values(args: ValidateMeanArealValuesInput):
    """Validate pixel coverage weights and mean areal values."""
    logger = get_run_logger()
    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok)))
        logger.info(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))

    ev = initialize_evaluation(temp_dir_path=args.temp_dir_path, start_spark_cluster=args.start_spark_cluster)
    store = get_readonly_repo_store(
        dest_bucket=args.dest_bucket,
        base_prefix=args.base_prefix,
        configuration_name=args.configuration_name,
        s3_storage_kwargs=args.s3_storage_kwargs
    )
    grid = xr.open_zarr(
        store, group=gu.read_data_group(store), decode_coords="all", chunks=None
    )[args.grid_variable_name].rio.set_spatial_dims(x_dim=args.x_dim, y_dim=args.y_dim)
    crs = CRS.from_user_input(grid.rio.crs.to_wkt())
    written = _written_steps(grid, args)[args.append_dim].to_index()

    # 1. Warehouse: aggregates in Spark, so only sampled basins come back to the driver
    ts_sdf = ev.table(
        args.timeseries_table_name, namespace_name=args.namespace_name, catalog_name=args.catalog_name
    ).filter([
        {"column": "configuration_name", "operator": "=", "value": args.configuration_name},
        {"column": "variable_name", "operator": "=", "value": args.grid_variable_name},
        {"column": "location_id", "operator": "like", "value": f"{args.location_id_prefix}-%"},
    ]).to_sdf()
    per_location = ts_sdf.groupBy("location_id").agg(
        F.count("*").alias("n"), F.sum(F.isnan("value").cast("int")).alias("nan")
    ).toPandas().set_index("location_id")
    locations = set(per_location.index)
    check("values exist", len(per_location) > 0, f"{int(per_location['n'].sum())} rows, {len(locations)} locations")
    check("no NaN values", per_location["nan"].sum() == 0)
    duplicates = ts_sdf.groupBy("location_id", "value_time", "reference_time", "member").count().filter("count > 1")
    check("no duplicate rows", duplicates.count() == 0)
    value_times = pd.to_datetime(ts_sdf.select("value_time").distinct().toPandas()["value_time"])
    check("value_time on written grid days", value_times.isin(written).all())

    for table, name in [
        ("configurations", args.configuration_name),
        ("variables", args.grid_variable_name),
        ("units", grid.attrs.get("units")),
    ]:
        n = ev.table(table, namespace_name=args.namespace_name, catalog_name=args.catalog_name).filter(
            {"column": "name", "operator": "=", "value": name}
        ).to_sdf().count()
        check(f"{table} has '{name}'", n == 1, f"{n} rows")
    self_crosswalks = set(
        ev.table("location_crosswalks", namespace_name=args.namespace_name, catalog_name=args.catalog_name)
        .to_sdf()
        .filter(F.col("primary_location_id") == F.col("secondary_location_id"))
        .select("secondary_location_id").toPandas()["secondary_location_id"]
    )
    check("self crosswalk for every location", locations <= self_crosswalks, f"{len(locations - self_crosswalks)} missing")

    # 2. Weights
    w_sdf = ev.table(WEIGHTS_TABLE_NAME).filter([
        {"column": "grid_name", "operator": "=", "value": args.grid_name},
        {"column": "location_id", "operator": "like", "value": f"{args.location_id_prefix}-%"},
    ]).to_sdf()
    check("weights unique per location and pixel", w_sdf.groupBy("location_id", "row", "col").count().filter("count > 1").count() == 0)
    check("fractions in (0, 1]", w_sdf.filter((F.col("fraction_covered") <= 0) | (F.col("fraction_covered") > 1 + 1e-6)).count() == 0)
    weighted_locations = set(w_sdf.select("location_id").distinct().toPandas()["location_id"])
    check("every location with values has weights", locations <= weighted_locations, f"{len(locations - weighted_locations)} missing")

    # Sample: half the basins with the fewest values (most likely dropped days), half random
    rng = np.random.default_rng(args.seed)
    by_count = per_location["n"].sort_values()
    edge = list(by_count.index[: args.n_basins // 2])
    rest = [loc for loc in by_count.index if loc not in edge]
    sample = edge + list(rng.choice(rest, size=min(len(rest), args.n_basins - len(edge)), replace=False))
    w = w_sdf.filter(F.col("location_id").isin(sample)).toPandas()
    ts = ts_sdf.filter(F.col("location_id").isin(sample)).select("location_id", "value_time", "value").toPandas()
    ts["value_time"] = pd.to_datetime(ts["value_time"])
    polys = ev.locations.filter({"column": "id", "operator": "in", "value": sample}).to_geopandas()
    polys = polys.to_crs(crs.to_wkt()).set_index("id")

    # Geodesic cell area per row of the regular grid; planar for projected grids
    ys, xs = grid[args.y_dim].values, grid[args.x_dim].values
    dy, dx = abs(ys[1] - ys[0]), abs(xs[1] - xs[0])
    if crs.is_geographic:
        geod = crs.get_geod()
        row_area = np.array([
            abs(geod.polygon_area_perimeter([0, dx, dx, 0], [y - dy / 2, y - dy / 2, y + dy / 2, y + dy / 2])[0])
            for y in ys
        ])

        def area_of(geom):
            return abs(geod.geometry_area_perimeter(geom)[0])
    else:
        row_area = np.full(ys.size, dx * dy)

        def area_of(geom):
            return geom.area
    order = np.argsort(ys)

    def cell_area(center_y):
        return np.interp(center_y, ys[order], row_area[order])

    grid_box = box(*grid.rio.bounds())
    weighted_area = (w["fraction_covered"] * row_area[w["row"].to_numpy()]).groupby(w["location_id"]).sum()
    inside_area = polys.geometry.apply(lambda g: area_of(g.intersection(grid_box)))
    ratio = weighted_area / inside_area.reindex(weighted_area.index)
    bad = ratio[(ratio - 1).abs() > 0.01]
    check(
        "weights area within 1% of polygon area in grid", bad.empty,
        f"{len(bad)} of {len(ratio)} outside, ratio {ratio.min():.5f} to {ratio.max():.5f}"
    )

    # 3. Values recomputed from the raw grid
    rows = []
    for loc in sample:
        poly = gpd.GeoDataFrame(geometry=[polys.loc[loc, "geometry"]], crs=crs.to_wkt())
        lw = w[w["location_id"] == loc]
        window = grid.isel({
            args.y_dim: slice(int(lw["row"].min()), int(lw["row"].max()) + 1),
            args.x_dim: slice(int(lw["col"].min()), int(lw["col"].max()) + 1),
        })
        first = window.isel({args.append_dim: 0}).rename({args.x_dim: "x", args.y_dim: "y"})
        ones = first.copy(data=np.ones(first.shape, "float32")).load().rio.write_crs(crs.to_wkt())
        full = exact_extract(ones, poly, ["coverage", "center_y"], output="pandas").iloc[0]
        total = float((np.asarray(full["coverage"]) * cell_area(np.asarray(full["center_y"]))).sum())

        stored = ts[ts["location_id"] == loc].set_index("value_time")["value"]
        in_span = written[(written >= stored.index.min()) & (written <= stored.index.max())]
        days = list(rng.choice(stored.index.to_numpy(), size=min(args.n_days, len(stored)), replace=False))
        days += list(in_span.difference(stored.index)[:5])
        values = window.sel({args.append_dim: days}).load()

        for day in values[args.append_dim].to_index():
            raster = values.sel({args.append_dim: day}).rename({args.x_dim: "x", args.y_dim: "y"})
            r = exact_extract(raster.rio.write_crs(crs.to_wkt()), poly, ["values", "coverage", "center_y"], output="pandas").iloc[0]
            # exactextract skips NaN cells, so this is the valid area only
            a = np.asarray(r["coverage"], float) * cell_area(np.asarray(r["center_y"], float))
            valid = float(a.sum())
            coverage = valid / total if total else 0.0
            rows.append({
                "location_id": loc,
                "value_time": day,
                "valid_coverage": coverage,
                "expect_dropped": coverage < args.min_valid_coverage,
                "expected": float((np.asarray(r["values"], float) * a).sum() / valid) if valid else np.nan,
                "stored": stored.get(day, np.nan),
            })

    cmp = pd.DataFrame(rows)
    judged = cmp[(cmp["valid_coverage"] - args.min_valid_coverage).abs() >= 0.005]
    kept = judged[~judged["expect_dropped"]]
    diff = (kept["stored"] - kept["expected"]).abs()
    ok = kept["stored"].notna() & (diff <= np.maximum(args.rel_tol * kept["expected"].abs(), args.abs_tol))
    rel = diff / kept["expected"].abs().clip(lower=args.abs_tol)
    check("recomputed values match the warehouse", ok.all(), f"{(~ok).sum()} of {len(kept)} differ; max rel diff {rel.max():.2e}")
    dropped = judged[judged["expect_dropped"]]
    check(
        "days below min_valid_coverage are absent", dropped["stored"].isna().all(),
        f"{len(dropped)} below threshold, {dropped['stored'].notna().sum()} stored anyway"
    )
    logger.info(f"{len(cmp)} basin-days in {len(sample)} basins; {len(cmp) - len(judged)} near the threshold not judged")
    if not ok.all():
        logger.info("Largest differences:\n" + kept.assign(rel_diff=rel).sort_values("rel_diff", ascending=False).head(10).to_string())

    failed = [name for name, passed in results if not passed]
    logger.info(f"{len(results) - len(failed)} of {len(results)} checks passed")
    if failed:
        raise ValueError(f"Validation failed: {failed}")
