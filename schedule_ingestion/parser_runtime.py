"""Fingerprint an installed parser and an immutable external resource directory."""
import hashlib
import importlib.metadata
from pathlib import Path
import platform
import sys


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def runtime_manifest(root, *, catalog_source):
    root = Path(root).resolve(strict=True)
    if not root.is_dir() or not (root / 'config').is_dir():
        raise ValueError('A dedicated parser resource directory with config is required')
    distribution = importlib.metadata.distribution('eazyclass-tableparser')
    code = {}
    for entry in distribution.files or ():
        relative = Path(str(entry))
        if relative.suffix != '.py':
            continue
        path = Path(distribution.locate_file(entry)).resolve(strict=True)
        parts = list(relative.with_suffix('').parts)
        if parts[-1] == '__init__':
            parts.pop()
        module = sys.modules.get('.'.join(parts))
        if module is not None and Path(module.__file__).resolve() != path:
            raise ValueError('Parser module is shadowed: ' + '.'.join(parts))
        code[relative.as_posix()] = file_hash(path)
    if not code:
        raise ValueError('Installed parser file inventory is required')
    resources = {}
    for path in sorted(root.rglob('*')):
        if '__pycache__' in path.parts or not path.is_file():
            continue
        if not path.resolve().is_relative_to(root):
            raise ValueError('Resource links must stay within their release directory')
        resources[path.relative_to(root).as_posix()] = file_hash(path)
    catalog_source = catalog_source.strip().rstrip('/')
    if not catalog_source:
        raise ValueError('Catalog source is required')
    return dict(format=1, catalog_source=catalog_source, parser_version=distribution.version, code=code, resources=resources,
                python=platform.python_version(), dependencies={
                    name: importlib.metadata.version(name)
                    for name in ('numpy', 'scikit-learn', 'joblib', 'PyYAML', 'jsonapi-client', 'python-dotenv')})
