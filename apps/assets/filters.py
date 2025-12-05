"""
Advanced filtering for IP assets using django-filter.
"""
import django_filters
from .models import IPAsset


class IPAssetFilter(django_filters.FilterSet):
    """Advanced filtering for IP assets."""
    
    # Text search
    title = django_filters.CharFilter(lookup_expr='icontains')
    description = django_filters.CharFilter(lookup_expr='icontains')
    
    # Creator filter - supports both user ID and wallet address
    creator = django_filters.CharFilter(method='filter_creator')
    
    def filter_creator(self, queryset, name, value):
        """
        Filter by creator - supports both user ID and wallet address.
        If value is numeric, treat as user ID. Otherwise, treat as wallet address.
        """
        try:
            # Try to parse as integer (user ID)
            creator_id = int(value)
            return queryset.filter(creator__id=creator_id)
        except (ValueError, TypeError):
            # Not a number, treat as wallet address
            return queryset.filter(creator__wallet_address__iexact=value)
    
    # Boolean filters
    is_derivative = django_filters.BooleanFilter()
    allow_derivatives = django_filters.BooleanFilter()
    commercial_rights = django_filters.BooleanFilter()
    
    # Registration status filter
    registration_status = django_filters.CharFilter(lookup_expr='iexact')
    
    # Royalty percentage range
    royalty_percentage_min = django_filters.NumberFilter(
        field_name='royalty_percentage',
        lookup_expr='gte'
    )
    royalty_percentage_max = django_filters.NumberFilter(
        field_name='royalty_percentage',
        lookup_expr='lte'
    )
    
    # Date filters
    created_after = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='gte'
    )
    created_before = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='lte'
    )
    
    # Ordering
    ordering = django_filters.OrderingFilter(
        fields=(
            ('created_at', 'created_at'),
            ('title', 'title'),
            ('royalty_percentage', 'royalty_percentage'),
        ),
        field_labels={
            'created_at': 'Created Date',
            'title': 'Title',
            'royalty_percentage': 'Royalty Percentage',
        }
    )

    class Meta:
        model = IPAsset
        fields = ['title', 'description', 'creator', 'is_derivative', 'allow_derivatives', 'commercial_rights']

