"""
Management command to create an SPG NFT collection for Story Protocol.

Run this ONCE to create a collection, then update your .env file with the returned address.

Usage:
    python manage.py create_spg_collection
    python manage.py create_spg_collection --name "My Collection" --symbol "MYC"
"""
from django.core.management.base import BaseCommand
from apps.assets.services.story_service import get_story_service


class Command(BaseCommand):
    help = 'Create an SPG NFT collection for Story Protocol IP registration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--name',
            type=str,
            default='Lore IP Collection',
            help='Collection name (default: "Lore IP Collection")'
        )
        parser.add_argument(
            '--symbol',
            type=str,
            default='LORE',
            help='Collection symbol (default: "LORE")'
        )
        parser.add_argument(
            '--contract-uri',
            type=str,
            default='',
            help='Contract URI for collection metadata (optional)'
        )
        parser.add_argument(
            '--private-minting',
            action='store_true',
            help='If set, only addresses with minter role can mint (default: public minting)'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Initializing Story Protocol service...'))

        try:
            story_service = get_story_service()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to initialize Story Protocol service: {e}'))
            self.stderr.write(self.style.WARNING(
                'Make sure STORY_PROTOCOL_PRIVATE_KEY is set in your .env file'
            ))
            return

        if not story_service.is_ready():
            self.stderr.write(self.style.ERROR(
                'Story Protocol service not ready. Check your configuration:\n'
                '- WEB3_PROVIDER_URI\n'
                '- STORY_PROTOCOL_PRIVATE_KEY\n'
                '- STORY_PROTOCOL_CHAIN_ID'
            ))
            return

        self.stdout.write(f'Creating collection: {options["name"]} ({options["symbol"]})')
        self.stdout.write(f'Account: {story_service.account.address}')

        try:
            result = story_service.create_spg_nft_collection(
                name=options['name'],
                symbol=options['symbol'],
                contract_uri=options['contract_uri'],
                is_public_minting=not options['private_minting'],
                mint_open=True,
            )

            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('=' * 60))
            self.stdout.write(self.style.SUCCESS('SPG NFT Collection created successfully!'))
            self.stdout.write(self.style.SUCCESS('=' * 60))
            self.stdout.write('')
            self.stdout.write(f'Collection Address: {result["nft_contract"]}')
            self.stdout.write(f'Transaction Hash:   {result["tx_hash"]}')
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('*** ACTION REQUIRED ***'))
            self.stdout.write(self.style.WARNING('Update your .env file with:'))
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(
                f'STORY_PROTOCOL_SPG_NFT_CONTRACT={result["nft_contract"]}'
            ))
            self.stdout.write('')
            self.stdout.write('Then restart your Django server for the changes to take effect.')

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to create collection: {e}'))
            self.stderr.write(self.style.WARNING(
                'Check that:\n'
                '- Your account has sufficient balance for gas fees\n'
                '- The network (Aeneid testnet) is accessible\n'
                '- Your private key is correct'
            ))
