import os
import datetime
import boto3
import io
import re
import uuid
from PIL import Image, UnidentifiedImageError
from pillow_heif import register_heif_opener
from botocore.exceptions import NoCredentialsError
from app.config import Config

# Register HEIF support
register_heif_opener()

def sanitize_filename(filename):
    """
    Sanitize filename by removing/replacing unsafe characters
    """
    if not filename:
        return "unnamed"
    
    # Get name without extension
    name = os.path.splitext(filename)[0]
    
    # Replace spaces with underscores
    name = name.replace(' ', '_')
    
    # Remove or replace special characters, keep only alphanumeric, underscore, hyphen
    name = re.sub(r'[^\w\-]', '', name)
    
    # Remove multiple consecutive underscores/hyphens
    name = re.sub(r'[_\-]+', '_', name)
    
    # Remove leading/trailing underscores/hyphens
    name = name.strip('_-')
    
    # Ensure name is not empty and not too long
    if not name:
        name = "image"
    elif len(name) > 50:
        name = name[:50]
    
    return name

def handle_image_upload(file):
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=Config.AWS_ACCESS_KEY,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION
        )

        # Sanitize the filename
        safe_name = sanitize_filename(file.filename)
        
        # Add timestamp for uniqueness
        now = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Add a short UUID for extra uniqueness (optional)
        short_uuid = str(uuid.uuid4())[:8]
        
        # Create safe filename
        unique_filename = f"{safe_name}_{now}_{short_uuid}.jpg"
        key = f"wave_length_assets/{unique_filename}"

        try:
            image = Image.open(file.stream)
        except UnidentifiedImageError:
            raise Exception("Invalid image file")

        # Convert to RGB and handle transparency
        if image.mode in ('RGBA', 'LA', 'P'):
            # Create a white background for transparent images
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = background
        else:
            image = image.convert("RGB")

        # Optional: Resize image if too large (to save bandwidth/storage)
        max_size = (1920, 1920)  # Max width/height
        if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Save to BytesIO with optimized quality
        image_io = io.BytesIO()
        image.save(image_io, format="JPEG", quality=85, optimize=True)
        image_io.seek(0)

        # Upload to S3
        s3.upload_fileobj(
            image_io,
            Config.AWS_S3_BUCKET_NAME,
            key,
            ExtraArgs={
                "ContentType": "image/jpeg",
                "CacheControl": "max-age=31536000"  # 1 year cache
            }
        )

        # Generate the safe URL
        image_url = f"https://{Config.AWS_S3_BUCKET_NAME}.s3.{Config.AWS_REGION}.amazonaws.com/{key}"
        
        return image_url

    except NoCredentialsError:
        raise Exception("AWS credentials not available")
    except Exception as e:
        raise Exception(f"Image upload failed: {str(e)}")
