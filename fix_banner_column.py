"""
Temporary script to add banner_url column to LoreUser table
Run this if migration state is out of sync with database
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from django.db import connection

def add_banner_url_column():
    """Add banner_url column if it doesn't exist"""
    with connection.cursor() as cursor:
        # Check if column exists
        cursor.execute("PRAGMA table_info(core_loreuser)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'banner_url' not in columns:
            print("Adding banner_url column...")
            cursor.execute("ALTER TABLE core_loreuser ADD COLUMN banner_url VARCHAR(200) NULL")
            print("Column added successfully!")
        else:
            print("Column banner_url already exists.")

if __name__ == '__main__':
    add_banner_url_column()

