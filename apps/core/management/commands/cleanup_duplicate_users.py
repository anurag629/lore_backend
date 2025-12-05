"""
Management command to clean up duplicate users with the same wallet address.
This can happen due to case sensitivity issues (e.g., 0xABC... vs 0xabc...).
"""
from django.core.management.base import BaseCommand
from apps.core.models import LoreUser


class Command(BaseCommand):
    help = 'Clean up duplicate users with the same wallet address (case-insensitive)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))
        
        # Find all users and group by lowercase wallet address
        all_users = LoreUser.objects.all().order_by('created_at')
        wallet_map = {}  # lowercase_address -> list of users
        
        for user in all_users:
            lower_address = user.wallet_address.lower()
            if lower_address not in wallet_map:
                wallet_map[lower_address] = []
            wallet_map[lower_address].append(user)
        
        # Find addresses with multiple users
        total_duplicates = 0
        total_deleted = 0
        
        for lower_address, users in wallet_map.items():
            if len(users) > 1:
                total_duplicates += 1
                self.stdout.write(
                    self.style.WARNING(f'\nFound {len(users)} users with address: {lower_address}')
                )
                
                # Keep the first user (oldest), delete the rest
                # Also consider keeping the one with the most data (assets, etc.)
                users_with_assets = []
                for user in users:
                    asset_count = user.assets.count() if hasattr(user, 'assets') else 0
                    users_with_assets.append((user, asset_count))
                
                # Sort by asset count (descending), then by created_at (ascending)
                users_with_assets.sort(key=lambda x: (-x[1], x[0].created_at))
                
                keep_user = users_with_assets[0][0]
                delete_users = [u for u, _ in users_with_assets[1:]]
                
                self.stdout.write(f'  Keeping: ID={keep_user.id}, wallet={keep_user.wallet_address}, '
                                  f'created={keep_user.created_at}, assets={users_with_assets[0][1]}')
                
                for user, asset_count in users_with_assets[1:]:
                    self.stdout.write(f'  Deleting: ID={user.id}, wallet={user.wallet_address}, '
                                      f'created={user.created_at}, assets={asset_count}')
                    if not dry_run:
                        # Transfer any assets to the kept user before deleting
                        if asset_count > 0:
                            user.assets.update(creator=keep_user)
                            self.stdout.write(self.style.SUCCESS(f'    Transferred {asset_count} assets to user {keep_user.id}'))
                        
                        user.delete()
                        total_deleted += 1
                
                # Normalize the kept user's wallet address
                if not dry_run and keep_user.wallet_address != lower_address:
                    keep_user.wallet_address = lower_address
                    keep_user.save(update_fields=['wallet_address'])
                    self.stdout.write(self.style.SUCCESS(f'  Normalized wallet address to lowercase'))
        
        # Summary
        self.stdout.write('')
        if total_duplicates == 0:
            self.stdout.write(self.style.SUCCESS('No duplicate users found!'))
        else:
            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f'Found {total_duplicates} wallet addresses with duplicates. '
                    f'Run without --dry-run to clean up.'
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f'Cleaned up {total_deleted} duplicate users from {total_duplicates} addresses.'
                ))
        
        # Also normalize all remaining wallet addresses to lowercase
        if not dry_run:
            updated = 0
            for user in LoreUser.objects.all():
                if user.wallet_address != user.wallet_address.lower():
                    user.wallet_address = user.wallet_address.lower()
                    user.save(update_fields=['wallet_address'])
                    updated += 1
            
            if updated > 0:
                self.stdout.write(self.style.SUCCESS(
                    f'Normalized {updated} wallet addresses to lowercase.'
                ))

