"""OpenAPI descriptions for authentication implemented by this application."""
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class HMACAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "scheduler.authentication.hmac_authentication.HMACAuthentication"
    # All four headers are required together (AND), not alternative credentials.
    name = ["hmacSignature", "hmacTimestamp", "hmacPlatform", "hmacSocialId"]

    def get_security_definition(self, auto_schema):
        headers = [
            ("X-Signature", "Hex HMAC-SHA256 of METHOD, path including query, timestamp, platform, "
             "social ID and hex SHA256 of the raw body, joined by newline characters. "
             "Compute with the platform secret outside Swagger UI; never enter the secret here. "
             "Recompute for each request."),
            ("X-Timestamp", "Unix timestamp in seconds; allowed clock difference is 180 seconds."),
            ("X-Platform", "Platform identifier configured on the server, e.g. telegram."),
            ("X-Social-ID", "User identifier on that platform."),
        ]
        return [{"type": "apiKey", "in": "header", "name": header, "description": description}
                for header, description in headers]
