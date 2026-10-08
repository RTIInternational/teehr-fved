CREATE TABLE IF NOT EXISTS grid_pixel_coverage_weights (
    fraction_covered DOUBLE,
    row INT,
    col INT,
    location_id STRING,
    configuration_name STRING,
    grid_name STRING,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
USING iceberg
PARTITIONED BY (grid_name);
