from rest_framework.renderers import JSONRenderer


class CustomJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get("response")
        success = 200 <= response.status_code < 300

        return super().render(
            {
                "success": success,
                "data": data if success else None,
                "errors": None if success else data,
                "message": response.status_text,
            }
        )
