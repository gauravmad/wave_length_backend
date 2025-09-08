import requests
import io
from PIL import Image
from typing import Optional, Dict


class ImageService:
    """Service class for handling image processing operations"""
    
    @staticmethod
    def download_and_process_image(image_url: str) -> Optional[Dict]:
        """Download image from URL and prepare it for Gemini API"""
        try:
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            image = Image.open(io.BytesIO(response.content))
            
            # Convert to RGB if necessary
            if image.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Save to buffer
            img_buffer = io.BytesIO()
            image.save(img_buffer, format='JPEG', quality=85)
            img_data = img_buffer.getvalue()
            
            return {
                "data": img_data,
                "mime_type": "image/jpeg"
            }
        except Exception as e:
            print(f"❌ Error processing image: {e}")
            return None