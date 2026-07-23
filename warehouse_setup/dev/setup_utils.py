from teehr.evaluation.spark_session_utils import create_spark_session

# primary location ids for FVED
DEV_LOCATION_ID_LIST = [
    # initial crmms locations w/ usgs record
    'usgs-09149500',
    'usgs-09361500',
    'usgs-09260050'
]



def create_minio_spark_session():
    """Start a Spark session with MinIO credentials and custom configuration."""
    
    return create_spark_session(
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin123",
    update_configs={
        "spark.hadoop.fs.s3a.aws.credentials.provider":
        "org.apache.hadoop.fs.s3a.AnonymousAWSCredentialsProvider"
    }
)