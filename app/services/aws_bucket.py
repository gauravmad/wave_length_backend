import os
import datetime
import boto3
import io
from PIL import Image, UnidentifiedImageError
from pillow_heif import register_heif_opener
from botocore.exceptions import NoCredentialsError
from app.config import Config

# Register HEIF support
register_heif_opener()

def handle_image_upload(file):
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=Config.AWS_ACCESS_KEY,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION
        )

        name, ext = os.path.splitext(file.filename)
        now = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{name}_{now}.jpg"
        key = f"wave_length_assets/{unique_filename}"

        try:
            image = Image.open(file.stream)
        except UnidentifiedImageError:
            raise Exception("Invalid image file")

        image = image.convert("RGB")  # Convert to JPEG compatible mode
        image_io = io.BytesIO()
        image.save(image_io, format="JPEG", quality=40)
        image_io.seek(0)

        s3.upload_fileobj(
            image_io,
            Config.AWS_S3_BUCKET_NAME,
            key,
            ExtraArgs={"ContentType": "image/jpeg"}
        )

        image_url = f"https://{Config.AWS_S3_BUCKET_NAME}.s3.{Config.AWS_REGION}.amazonaws.com/{key}"
        return image_url

    except NoCredentialsError:
        raise Exception("AWS credentials not available")
    except Exception as e:
        raise Exception(f"Image upload failed: {str(e)}")
