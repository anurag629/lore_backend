"""
Custom middleware for Azure App Service compatibility.
"""
from django.http import HttpResponse
import re


class AzureHealthCheckMiddleware:
    """
    Middleware to handle Azure App Service health checks.

    Azure uses internal IPs (169.254.x.x) to check container health
    by requesting /robots933456.txt. These IPs are not in ALLOWED_HOSTS
    and Django doesn't support IP wildcards.

    This middleware intercepts health check requests and returns 200 OK
    before Django's SecurityMiddleware validates the host.
    """

    # Azure health check path
    HEALTH_CHECK_PATH = '/robots933456.txt'

    # Azure internal IP pattern (link-local addresses)
    AZURE_INTERNAL_IP_PATTERN = re.compile(r'^169\.254\.\d+\.\d+')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if this is an Azure health check
        if self._is_azure_health_check(request):
            return HttpResponse('OK', status=200, content_type='text/plain')

        return self.get_response(request)

    def _is_azure_health_check(self, request):
        """
        Determine if request is an Azure health check.

        Conditions:
        1. Path is /robots933456.txt (Azure's health check path)
        2. Host is an Azure internal IP (169.254.x.x)

        Note: We use request.META directly instead of request.get_host()
        because get_host() triggers Django's host validation.
        """
        # Check path
        if request.path != self.HEALTH_CHECK_PATH:
            return False

        # Get host from META without triggering validation
        # HTTP_HOST format: "169.254.130.2:8000" or "169.254.130.2"
        http_host = request.META.get('HTTP_HOST', '')
        host = http_host.split(':')[0]  # Remove port if present

        if self.AZURE_INTERNAL_IP_PATTERN.match(host):
            return True

        return False
