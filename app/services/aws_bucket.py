import os
import datetime
import boto3
from botocore.exceptions import NoCredentialsError
from app.config import Config

def handle_image_upload(file):
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id = Config.AWS_ACCESS_KEY,
            aws_secret_access_key = Config.AWS_SECRET_ACCESS_KEY,
            region_name = Config.AWS_REGION
        )

        name,ext = os.path.splitext(file.filename)
        now = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{name}_{now}{ext}"

        key = f"wave_length_assets/{unique_filename}"

        s3.upload_fileobj(
            file,
            Config.AWS_S3_BUCKET_NAME,
            key,
            ExtraArgs={"ContentType": file.content_type}
        )

        image_url=f"https://{Config.AWS_S3_BUCKET_NAME}.s3.{Config.AWS_REGION}.amazonaws.com/{key}"
        return image_url

    except NoCredentialsError:
        raise Exception("AWS credentials not available")    
