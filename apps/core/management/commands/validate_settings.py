"""
Django management command to validate application settings.
Useful for CI/CD pipelines and deployment verification.
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from config.settings.validator import SettingsValidator


class Command(BaseCommand):
    help = 'Validate application settings and configuration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--environment',
            type=str,
            default=None,
            choices=['development', 'production'],
            help='Environment to validate for (defaults to auto-detect from DEBUG setting)'
        )

    def handle(self, *args, **options):
        environment = options['environment']

        # Auto-detect environment if not specified
        if environment is None:
            environment = 'development' if settings.DEBUG else 'production'

        self.stdout.write(
            self.style.WARNING(f'\nValidating settings for {environment} environment...\n')
        )

        validator = SettingsValidator()

        try:
            validator.validate_all(environment=environment)
            self.stdout.write(
                self.style.SUCCESS('✓ All settings validated successfully!\n')
            )
            self.stdout.write('Configuration is ready for deployment.')

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'✗ Settings validation failed:\n')
            )
            self.stdout.write(str(e))
            exit(1)
