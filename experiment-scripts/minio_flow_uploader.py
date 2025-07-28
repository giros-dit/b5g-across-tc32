import json
import time
import boto3

# Import MinIO configuration from config file
from config.b5g import S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET

# Create S3 client (same as your existing code)
s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name='local'
)

# Flag to ensure we only upload once per session
_initial_flows_created = False

def create_initial_flows_file(dst_ips):
    """
    Create and upload initial flows JSON to S3 - ONLY THE FIRST TIME "Start Variation" is clicked
    After this, ALL operations are handled via HTTP API, this method is NEVER used again.
    """
    global _initial_flows_created
    
    print(f"[MINIO_DEBUG] ========== create_initial_flows_file LLAMADA ==========")
    print(f"[MINIO_DEBUG] _initial_flows_created = {_initial_flows_created}")
    
    # Only create the initial file once per session
    if _initial_flows_created:
        print("[MINIO_DEBUG] *** Ya creado en esta sesión - SALTANDO ***")
        return
    
    print("[MINIO_DEBUG] *** CREANDO ARCHIVO INICIAL - PRIMERA VEZ EN ESTA SESIÓN ***")
    
    # Use the same timestamp for all flows
    current_timestamp = time.time()
    
    flows_data = {
        "flows": [],
        "inactive_routers": []
    }
    
    # Create flow entries for each destination IP with same timestamp
    for dst_ip in dst_ips:
        flow_entry = {
            "_id": dst_ip,
            "version": 2,
            "timestamps": {
                "ts_api_created": current_timestamp
            }
        }
        flows_data["flows"].append(flow_entry)
    
    # Upload to S3
    content = json.dumps(flows_data, indent=4)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    file_key = f"flows/flows_{timestamp}.json"
    
    print(f"[MINIO_DEBUG] Subiendo archivo: {file_key}")
    s3_client.put_object(
        Bucket=S3_BUCKET, 
        Key=file_key, 
        Body=content.encode("utf-8")
    )
    
    print(f"[MINIO_DEBUG] ✓ ARCHIVO CREADO: s3://{S3_BUCKET}/{file_key}")
    print(f"[MINIO_DEBUG] ✓ {len(flows_data['flows'])} flujos con timestamp: {current_timestamp}")
    
    # Mark as created - won't create again in this session
    _initial_flows_created = True
    print(f"[MINIO_DEBUG] ✓ Variable _initial_flows_created = {_initial_flows_created}")
    print(f"[MINIO_DEBUG] ========== create_initial_flows_file COMPLETADO ==========")

def monitor_s3_files():
    """Función de debug para listar archivos en S3"""
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix="flows/")
        if 'Contents' in response:
            print(f"[MINIO_DEBUG] === ARCHIVOS ACTUALES EN S3/flows/ ===")
            for obj in response['Contents']:
                print(f"[MINIO_DEBUG] - {obj['Key']} (LastModified: {obj['LastModified']})")
        else:
            print(f"[MINIO_DEBUG] === NO HAY ARCHIVOS EN S3/flows/ ===")
    except Exception as e:
        print(f"[MINIO_DEBUG] Error listando S3: {e}")

def log_current_stack(message):
    """Log quien está llamando esta función"""
    import traceback
    print(f"[STACK_TRACE] {message}")
    for line in traceback.format_stack()[-5:-1]:  # Últimas 4 llamadas
        print(f"[STACK_TRACE] {line.strip()}")
    print(f"[STACK_TRACE] ====================")