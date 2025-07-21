__name__ = "B5G-ACROSS-TC32 -- Experiment data to CSV aggregator"
__version__ = "0.0.2"
__author__ = "David Martínez García <https://github.com/david-martinez-garcia>"
__credits__ = [
    "GIROS DIT-UPM <https://github.com/giros-dit>",
    "Luis Bellido Triana <https://github.com/lbellido>",
    "Pablo Fernández López <https://github.com/pablofl01>",
    "Mario Vicente Albertos <https://github.com/mariov22>",
    "Alejandro Villaseca Martínez <https://github.com/avillaseca01>",
    "Daniel González Sánchez <https://github.com/daniel-gonzalez-sanchez>",
    "Carlos Mariano Lentisco Sánchez <https://github.com/clentisco>"
]

## -- BEGIN IMPORT STATEMENTS -- ##

import boto3
import csv
import json
import logging
import os
import re

## -- END IMPORT STATEMENTS -- ##

## -- BEGIN LOGGING CONFIGURATION -- ##

logger = logging.getLogger(__name__)
logging.basicConfig(
    format = '%(asctime)s %(levelname)-8s %(message)s',
    level = logging.DEBUG,
    datefmt = '%d-%m-%Y %H:%M:%S'
)

## -- END LOGGING CONFIGURATION -- ##

## -- BEGIN CONSTANTS DEFINITION -- ##

### --- S3 STORAGE CONFIGURATION --- ###

S3_ENDPOINT = os.getenv("S3_ENDPOINT")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")

# Experiment data are saved in independent buckets.
# The name of the bucket will be the name/ID of the experiment.
S3_BUCKET = os.getenv("S3_BUCKET")

### --- --- ###

### --- CSV HEADERS --- ###

CSV_HEADERS = ["experiment_id", "router_id", "epoch_timestamp", "power_consumption_watts"]

### --- --- ###

## -- END CONSTANTS DEFINITION -- ##

## -- BEGIN MAIN CODE -- ##

logger.info("Script executed.")

logger.info("---")

# Initialize S3 client:
logger.info("Initializing S3 client...")
s3_client = boto3.client(
    "s3",
    endpoint_url = S3_ENDPOINT,
    aws_access_key_id = S3_ACCESS_KEY,
    aws_secret_access_key = S3_SECRET_KEY,
    region_name = "local" 
)
logger.info("Done.")

logger.info("---")

# Create output CSV file and write headers line:
logger.info("Creating output CSV file and writer object...")
csv_output_file = open(file = S3_BUCKET + ".csv", mode = "w", newline = "")
csv_writer = csv.writer(csv_output_file)
logger.info("Done.")

logger.info("---")

logger.info("Writing headers to CSV file...")
csv_writer.writerow(CSV_HEADERS)
logger.info("Done.")

logger.info("---")

# Get JSON files from S3 storage. These files contain the desired router metrics that are to be aggregated
# in the output CSV file.
# Help: https://stackoverflow.com/questions/36205481/read-file-content-from-s3-bucket-with-boto3
try:
    # logger.info("Trying to retrieve JSON files from S3 storage...")
    logger.info("Building paginator and regex to retrieve JSON files from S3 storage...")
    # Metrics files are under folders named ML_rX, being "X" the number of the router.
    # The prefix specifies that keys must start with the string "ML_r".
    # If we want to filter to specific routers, we can use a regular expression.
    pattern = re.compile(r'^ML_r\d+/')
    # A paginator is used in case the number of files to retrieve is very large.
    paginator = s3_client.get_paginator("list_objects_v2")
    
    logger.info("Done.")

    logger.info("---")

    logger.info("Trying to retrieve files...")
    logger.info("---")
    for page in paginator.paginate(Bucket = S3_BUCKET, Prefix = "ML_r"):
        for object in page.get("Contents"):
            key = object.get("Key")
            logger.info("File retrieved: " + key)
            if pattern.match(key):
                logger.info("File key/name matches regular expression.")
                logger.info("Trying to retrieve data from JSON file...")
                data = s3_client.get_object(Bucket = S3_BUCKET, Key = key)
                metrics_content = json.loads(data["Body"].read().decode("utf-8").strip())
                logger.info("Done.")

            # For every retrieved JSON file, parse it to get metrics and write them to output CSV file.
            logger.info("Trying to parse JSON data and retrieve desired metrics...")
            experiment_id = metrics_content["experiment_id"]
            router_id = metrics_content["node_exporter"].split(":")[0]
            epoch_timestamp = metrics_content["epoch_timestamp"]
            for output_ml_metric in metrics_content["output_ml_metrics"]:
                if output_ml_metric["name"] == "node_network_power_consumption":
                    power_consumption_watts = output_ml_metric["value"]
            csv_metrics = [
                experiment_id,
                router_id,
                epoch_timestamp,
                power_consumption_watts
            ]
            logger.info("Done.")

            logger.info("Trying to write metrics to output CSV file...")
            csv_writer.writerow(csv_metrics)
            logger.info("Done.")

            logger.info("---")

    logger.info("Done.")

    logger.info("---")

    # Finally, the output CSV file is closed:
    logger.info("Closing output CSV file...")
    csv_output_file.close()
    logger.info("Done.")
    
    logger.info("---")
except Exception as e:
    logger.exception(f"Exception while retrieving data from S3 storage: {e}")

logger.info("All done.")

## -- END MAIN CODE -- ##
