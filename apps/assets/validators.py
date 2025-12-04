"""
Validators for IP Asset file uploads and data validation.
"""
from django.core.exceptions import ValidationError
from django.conf import settings
import os

# Constants
MAX_FILE_SIZE = getattr(settings, 'MAX_FILE_SIZE', 50 * 1024 * 1024)  # 50MB default
ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
ALLOWED_VIDEO_TYPES = ['video/mp4', 'video/webm', 'video/quicktime']
ALLOWED_TYPES = ALLOWED_IMAGE_TYPES + ALLOWED_VIDEO_TYPES


def validate_file_size(file):
    """
    Validate file size.
    
    Args:
        file: Django uploaded file object
        
    Raises:
        ValidationError: If file size exceeds maximum allowed size
    """
    if file.size > MAX_FILE_SIZE:
        max_size_mb = MAX_FILE_SIZE / (1024 * 1024)
        raise ValidationError(
            f'File size ({file.size / (1024*1024):.2f}MB) exceeds maximum allowed size of {max_size_mb}MB'
        )


def validate_file_type(file):
    """
    Validate file MIME type.
    
    Args:
        file: Django uploaded file object
        
    Returns:
        str: MIME type of the file
        
    Raises:
        ValidationError: If file type is not allowed
    """
    # Try to use python-magic if available
    try:
        import magic
        file.seek(0)
        file_content = file.read(2048)
        file.seek(0)  # Reset file pointer
        
        mime_type = magic.from_buffer(file_content, mime=True)
    except ImportError:
        # Fallback to content_type if python-magic not available
        mime_type = file.content_type
    
    if mime_type not in ALLOWED_TYPES:
        raise ValidationError(
            f'File type {mime_type} not allowed. Allowed types: {", ".join(ALLOWED_TYPES)}'
        )
    
    return mime_type


def validate_file_name(file):
    """
    Validate file name for security.
    
    Args:
        file: Django uploaded file object
        
    Raises:
        ValidationError: If file name is invalid or contains security risks
    """
    # Check for path traversal attempts
    if '..' in file.name or '/' in file.name or '\\' in file.name:
        raise ValidationError('Invalid file name: path traversal detected')
    
    # Check file extension
    ext = os.path.splitext(file.name)[1].lower()
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.webm', '.mov']
    
    if ext not in allowed_extensions:
        raise ValidationError(f'File extension {ext} not allowed. Allowed extensions: {", ".join(allowed_extensions)}')
    
    # Check for dangerous characters
    dangerous_chars = ['<', '>', ':', '"', '|', '?', '*']
    for char in dangerous_chars:
        if char in file.name:
            raise ValidationError(f'Invalid file name: contains dangerous character "{char}"')


def validate_media_url(url):
    """
    Validate media URL format.
    
    Args:
        url: URL string to validate
        
    Raises:
        ValidationError: If URL format is invalid
    """
    from django.core.validators import URLValidator
    
    validator = URLValidator()
    try:
        validator(url)
    except ValidationError:
        raise ValidationError('Invalid media_url format. Must be a valid URL.')

