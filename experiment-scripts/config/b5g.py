# Network configuration parameters

# MAC addresses
SRC_MAC = "02:00:00:00:01:aa"
DST_MAC = "02:00:00:00:02:aa"

# Device MAC addresses
R1_MAC = SRC_MAC
R2_MAC = "02:00:00:00:01:ff"

# IP addresses
SRC_IP = "fd00:0:1::3"
DST_IPS = [f"fd00:0:2::b{str(i)}" for i in range(2, 12)]

# Device IP configuration
R1_IP = SRC_IP
R1_GATEWAY = "fd00:0:1::1"
R2_IP = "fd00:0:2::b1"
R2_GATEWAY = "fd00:0:2::1"
IP_PREFIX = 64

# API configuration
IXIA_API_LOCATION = "https://x.x.x.x:xxxx"
NCS_API_LOCATION = "http://x.x.x.x:xxxx"

# MINIO
S3_ENDPOINT = "http://x.x.x.x:xxxx"
S3_ACCESS_KEY = "<your_access_key>"
S3_SECRET_KEY = "<your_secret_key>"
S3_API = "s3v4"
S3_PATH = "auto"
S3_BUCKET = "<your_bucket_name>"