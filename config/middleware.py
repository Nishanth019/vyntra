from django.http import HttpResponse


class HealthCheckMiddleware:
    """Answer the load balancer's /healthz/ probe before ALLOWED_HOSTS validation.

    Platform probes hit the container by internal IP, which isn't in ALLOWED_HOSTS.
    The check deliberately skips the DB so a brief DB blip doesn't make the platform
    restart otherwise healthy instances.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthz/":
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)
