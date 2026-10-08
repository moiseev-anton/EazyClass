from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


def runtime_profile(environ):
    root = environ.get('TABLEPARSER_RESOURCE_ROOT', '').strip()
    source = environ.get('TABLEPARSER_CATALOG_SOURCE', '').strip().rstrip('/')
    if not root and not source:
        return None
    if not root or not source or not Path(root).is_absolute():
        raise ImproperlyConfigured('Set an absolute TABLEPARSER_RESOURCE_ROOT and TABLEPARSER_CATALOG_SOURCE together')
    return {'resource_root': root, 'catalog_source': source}
