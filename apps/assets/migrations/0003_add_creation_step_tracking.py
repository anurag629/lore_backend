# Generated manually for creation step tracking

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='ipasset',
            name='creation_step',
            field=models.CharField(
                choices=[
                    ('media_upload', 'Media Upload to IPFS'),
                    ('db_save', 'Database Save'),
                    ('metadata_upload', 'Metadata Upload to IPFS'),
                    ('story_registration', 'Story Protocol Registration'),
                    ('license_attachment', 'License Terms Attachment'),
                    ('completed', 'Completed'),
                ],
                db_index=True,
                default='media_upload',
                help_text='Current step in the creation process',
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name='ipasset',
            name='failed_at_step',
            field=models.CharField(
                blank=True,
                choices=[
                    ('media_upload', 'Media Upload to IPFS'),
                    ('db_save', 'Database Save'),
                    ('metadata_upload', 'Metadata Upload to IPFS'),
                    ('story_registration', 'Story Protocol Registration'),
                    ('license_attachment', 'License Terms Attachment'),
                    ('completed', 'Completed'),
                ],
                db_index=True,
                help_text='Step where creation failed (if any)',
                max_length=30,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='ipasset',
            name='media_ipfs_hash',
            field=models.CharField(
                blank=True,
                help_text='IPFS hash of the media file (for retry purposes)',
                max_length=66,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='ipasset',
            name='step_data',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Stores intermediate results from each creation step (IPFS URLs, hashes, etc.)',
            ),
        ),
        migrations.AddIndex(
            model_name='ipasset',
            index=models.Index(
                fields=['creation_step', 'registration_status'],
                name='assets_ipas_creatio_123abc_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='ipasset',
            index=models.Index(
                fields=['failed_at_step'],
                name='assets_ipas_failed__456def_idx',
            ),
        ),
    ]

