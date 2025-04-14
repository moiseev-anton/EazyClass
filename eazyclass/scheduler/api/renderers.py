from rest_framework.renderers import JSONRenderer
from datetime import datetime, timezone
import uuid


class APIJSONRenderer(JSONRenderer):
    media_type = 'application/json'
    charset = 'utf-8'

    # Статическая ссылка на документацию
    API_DOCS_URL = None

    def render(self, data, accepted_media_type=None, renderer_context=None):
        renderer_context = renderer_context or {}
        response = renderer_context.get('response')
        request = renderer_context.get('request')
        view = renderer_context.get('view')

        # Базовая структура ответа
        response_data = {
            'data': None,
            'errors': None,
            'links': self._build_links(request, view, data),
            'meta': {
                'status': response.status_code if response else 200,
                'timestamp': datetime.now().isoformat(),
                'request_id': self._get_request_id(request),
            }
        }

        # Проверяем, являются ли данные ошибками
        if isinstance(data, dict) and "errors" in data:
            response_data['errors'] = data["errors"]
        else:
            response_data['data'] = data

        # Добавление пагинации в meta
        pagination_data = self._get_pagination_data(view, data)
        if pagination_data:
            response_data['meta']['pagination'] = pagination_data

        return super().render(response_data, accepted_media_type, renderer_context)

    def _get_request_id(self, request):
        """Генерация или получение request_id"""
        if hasattr(request, 'META'):
            return str(request.META.get('HTTP_X_REQUEST_ID', uuid.uuid4()))
        return str(uuid.uuid4())

    def _build_links(self, request, view, data):
        """Формирование ссылок"""
        links = {
            'self': request.build_absolute_uri() if hasattr(request, 'build_absolute_uri') else None,
            'docs': self.API_DOCS_URL
        }

        # Добавление ссылок пагинации
        if hasattr(view, 'paginator') and view.paginator:
            paginator = view.paginator
            links['next'] = paginator.get_next_link() if hasattr(paginator, 'get_next_link') else None
            links['previous'] = paginator.get_previous_link() if hasattr(paginator, 'get_previous_link') else None

        # Поддержка кастомных ссылок из представления
        extra_links = getattr(view, 'extra_links', {})
        if callable(extra_links):
            extra_links = extra_links(request, data)
        links.update(extra_links)

        return links

    def _get_pagination_data(self, view, data):
        """Извлечение данных пагинации"""
        if hasattr(view, 'paginator') and view.paginator:
            paginator = view.paginator
            count = paginator.count if hasattr(paginator, 'count') else None
            page = paginator.page.number if hasattr(paginator, 'page') and paginator.page else None
            per_page = paginator.page.paginator.per_page if hasattr(paginator, 'page') and paginator.page else None
            if count is not None:
                return {
                    'count': count,
                    'page': page,
                    'per_page': per_page
                }
        return None
