"""
API views for Royalty Payment management.
Read-only views for viewing royalty payment history.
"""
import logging
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from ..models import RoyaltyPayment
from ..serializers import RoyaltyPaymentSerializer

logger = logging.getLogger(__name__)


class RoyaltyPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing royalty payment history.
    Read-only - payments are created by blockchain event listeners.
    """

    queryset = RoyaltyPayment.objects.select_related('asset', 'recipient').all()
    serializer_class = RoyaltyPaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter royalty payments for current user."""
        return super().get_queryset().filter(recipient=self.request.user)
