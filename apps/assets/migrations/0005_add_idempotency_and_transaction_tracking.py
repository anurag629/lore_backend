# Generated manually for idempotency and transaction tracking fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0004_rename_assets_ipas_creatio_123abc_idx_assets_ipas_creatio_ef1653_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='ipasset',
            name='idempotency_key',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Idempotency key for preventing duplicate blockchain transactions',
                max_length=64,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name='ipasset',
            name='transaction_nonce',
            field=models.IntegerField(
                blank=True,
                help_text='Blockchain transaction nonce for replay protection',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='ipasset',
            name='transaction_hash',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Primary blockchain transaction hash for this asset',
                max_length=66,
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name='ipasset',
            index=models.Index(
                fields=['idempotency_key'],
                name='assets_ipas_idempot_abc123_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='ipasset',
            index=models.Index(
                fields=['transaction_hash'],
                name='assets_ipas_transac_def456_idx',
            ),
        ),
    ]
