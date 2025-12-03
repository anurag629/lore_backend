"""
Django management command to create a superuser for Lore platform.

Usage:
    python manage.py create_superuser

With environment variables:
    DJANGO_SUPERUSER_WALLET=0x... python manage.py create_superuser

With command line arguments:
    python manage.py create_superuser --wallet 0x... --username admin --email admin@example.com --password yourpassword
"""
import os
import getpass
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from apps.core.models import LoreUser


class Command(BaseCommand):
    help = 'Create a superuser for Django admin with wallet address'

    def add_arguments(self, parser):
        parser.add_argument(
            '--wallet',
            type=str,
            help='Ethereum wallet address (0x...)',
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Username for the superuser',
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Email address for the superuser',
        )
        parser.add_argument(
            '--password',
            type=str,
            help='Password for Django admin login',
        )
        parser.add_argument(
            '--noinput',
            action='store_true',
            help='Create superuser without prompting for input',
        )

    def handle(self, *args, **options):
        # Get values from command line arguments or environment variables or defaults
        wallet_address = (
            options.get('wallet') or
            os.environ.get('DJANGO_SUPERUSER_WALLET') or
            '0x0000000000000000000000000000000000000000'  # Default wallet for development
        )

        username = (
            options.get('username') or
            os.environ.get('DJANGO_SUPERUSER_USERNAME') or
            'admin'
        )

        email = (
            options.get('email') or
            os.environ.get('DJANGO_SUPERUSER_EMAIL') or
            'admin@lore.local'
        )

        password = (
            options.get('password') or
            os.environ.get('DJANGO_SUPERUSER_PASSWORD')
        )

        noinput = options.get('noinput')

        # Normalize wallet address
        wallet_address = wallet_address.lower()

        # Check if superuser already exists
        if LoreUser.objects.filter(wallet_address=wallet_address).exists():
            self.stdout.write(
                self.style.WARNING(
                    f'Superuser with wallet address {wallet_address} already exists!'
                )
            )
            return

        if LoreUser.objects.filter(is_superuser=True).exists():
            self.stdout.write(
                self.style.WARNING(
                    'A superuser already exists in the database!'
                )
            )
            if not noinput:
                confirm = input('Do you want to create another superuser? (yes/no): ')
                if confirm.lower() != 'yes':
                    self.stdout.write(self.style.ERROR('Superuser creation cancelled.'))
                    return

        # Prompt for input if not using --noinput flag
        if not noinput:
            self.stdout.write(self.style.SUCCESS('\nCreating superuser for Lore platform\n'))

            # Prompt for wallet address
            wallet_input = input(f'Ethereum wallet address (default: {wallet_address}): ').strip()
            if wallet_input:
                wallet_address = wallet_input.lower()

            # Prompt for username
            username_input = input(f'Username (default: {username}): ').strip()
            if username_input:
                username = username_input

            # Prompt for email
            email_input = input(f'Email (default: {email}): ').strip()
            if email_input:
                email = email_input

            # Prompt for password (securely)
            if not password:
                while True:
                    password = getpass.getpass('Password for Django admin: ')
                    password_confirm = getpass.getpass('Password (again): ')
                    if password != password_confirm:
                        self.stdout.write(self.style.ERROR("Passwords don't match. Please try again."))
                    elif len(password) < 8:
                        self.stdout.write(self.style.ERROR("Password must be at least 8 characters long."))
                    else:
                        break
        else:
            # Non-interactive mode - require password
            if not password:
                password = 'admin123'  # Default password for development
                self.stdout.write(
                    self.style.WARNING(
                        f'\nNo password provided. Using default password: {password}\n'
                        'WARNING: Change this password immediately in production!\n'
                    )
                )

        # Validate wallet address format
        if not wallet_address.startswith('0x') or len(wallet_address) != 42:
            self.stdout.write(
                self.style.ERROR(
                    'Invalid wallet address format! Must start with 0x and be 42 characters long.'
                )
            )
            return

        # Create superuser
        try:
            superuser = LoreUser.objects.create(
                wallet_address=wallet_address,
                username=username,
                email=email,
                is_staff=True,
                is_superuser=True,
                is_active=True,
            )

            # Set password for Django admin login
            superuser.set_password(password)
            superuser.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ Superuser created successfully!\n'
                    f'  Wallet Address: {superuser.wallet_address}\n'
                    f'  Username: {superuser.username}\n'
                    f'  Email: {superuser.email}\n'
                )
            )

            self.stdout.write(
                self.style.SUCCESS(
                    '\n' + '='*60 + '\n'
                    'Django Admin Login Credentials:\n'
                    '='*60 + '\n'
                    f'  URL: http://localhost:8000/admin/\n'
                    f'  Username: {superuser.username}\n'
                    f'  Password: {"(hidden)" if not noinput or password != "admin123" else password}\n'
                    '='*60 + '\n'
                )
            )

            self.stdout.write(
                self.style.WARNING(
                    '\nNote: Lore also supports wallet-based authentication (SIWE).\n'
                    'For the main app, you can sign in with the wallet address above using MetaMask.\n'
                    'Make sure you have access to this wallet!\n'
                )
            )

        except IntegrityError as e:
            self.stdout.write(
                self.style.ERROR(
                    f'Error creating superuser: {str(e)}\n'
                    f'A user with this wallet address may already exist.'
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'Unexpected error creating superuser: {str(e)}'
                )
            )
