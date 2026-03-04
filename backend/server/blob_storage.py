import io
from minio import Minio
from minio.error import S3Error
import os

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9005")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)

def ensure_bucket_exists(bucket_name: str):
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)

def upload_text(bucket_name: str, object_name: str, content: str) -> str:
    """Uploads a string content to Minio and returns the object name."""
    ensure_bucket_exists(bucket_name)
    content_bytes = content.encode('utf-8')
    client.put_object(
        bucket_name,
        object_name,
        data=io.BytesIO(content_bytes),
        length=len(content_bytes),
        content_type="text/plain"
    )
    return object_name

def download_text(bucket_name: str, object_name: str) -> str:
    """Downloads a text object from Minio and returns its content as a string."""
    try:
        response = client.get_object(bucket_name, object_name)
        return response.read().decode('utf-8')
    except S3Error as e:
        print(f"Error downloading {object_name} from {bucket_name}: {e}")
        return ""
    finally:
        if 'response' in locals():
            response.close()
            response.release_conn()
