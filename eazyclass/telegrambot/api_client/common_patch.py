from jsonapi_client import common


def camelize_name(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def decamelize_name(name: str) -> str:
    import re

    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


# Monkey-патч для jsonapi_client:
# По умолчанию библиотека превращает поля с подчеркиваниями (short_title) в JSON-ключи с дефисами (short-title).
# Так как DRF JSON API настроен на camelCase (shortTitle), переопределяем функции сериализации,
# чтобы атрибуты корректно отображались и были доступны как обычные свойства: faculty.short_title.
common.jsonify_attribute_name = camelize_name
common.dejsonify_attribute_name = decamelize_name
