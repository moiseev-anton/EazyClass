from drf_spectacular.openapi import AutoSchema
from drf_spectacular_jsonapi.schemas.openapi import JsonApiAutoSchema
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer
from rest_framework_json_api.parsers import JSONParser as JSONAPIParser
from rest_framework_json_api.renderers import JSONRenderer as JSONAPIRenderer


class JsonApiViewMixin:
    parser_classes = [JSONAPIParser]
    renderer_classes = [JSONAPIRenderer]
    schema = JsonApiAutoSchema()


class PlainApiViewMixin:
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]
    schema = AutoSchema()
