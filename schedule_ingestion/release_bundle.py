"""Build and verify a portable parser release without Django settings or network."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(root):
    root = Path(root).resolve(strict=True)
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Release files must not be symlinks')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha256(path)
    return result


def verify_bundle(manifest_path, expected_sha256):
    manifest_path = Path(manifest_path).resolve(strict=True)
    if sha256(manifest_path) != expected_sha256:
        raise ValueError('Release manifest checksum differs')
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    if data.get('format') != 1 or not isinstance(data.get('files'), dict):
        raise ValueError('Unknown release format')
    actual = inventory(manifest_path.parent)
    actual.pop(manifest_path.name)
    if actual != data['files']:
        raise ValueError('Release inventory differs: missing, extra or changed files')
    for key in ('wheel', 'knowledge'):
        if data.get(key) not in data['files']:
            raise ValueError('Release artifact is absent from inventory')
    return data


def build_bundle(*, wheel, wheel_sha256, resources, knowledge, install_report, output):
    wheel, resources, knowledge, install_report, output = map(Path, (wheel, resources, knowledge, install_report, output))
    if output.exists():
        raise ValueError('Use a new release directory; never overwrite a release')
    if output.resolve().is_relative_to(resources.resolve()):
        raise ValueError('Output must be outside the original resources')
    if sha256(wheel) != wheel_sha256:
        raise ValueError('Wheel checksum differs from the approved artifact')
    knowledge_hash = sha256(knowledge)
    inputs = inventory(resources)
    if not any(name.startswith('config/') for name in inputs):
        raise ValueError('Resource directory must include config')
    if any(name != 'data/knowledge.sqlite3' and '.sqlite' in name for name in inputs):
        raise ValueError('Unexpected SQLite artifact in resource directory')
    # The seed is selected explicitly. A resource directory may contain a local
    # database from another run; it is never the server's source of knowledge.
    report = json.loads(install_report.read_text(encoding='utf-8'))
    dependencies = {}
    for item in report['install']:
        name, version = item['metadata']['name'], item['metadata']['version']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or not re.fullmatch(r'[A-Za-z0-9_.+!-]+', version):
            raise ValueError('Unexpected dependency identifier')
        normalized = re.sub(r'[-_.]+', '-', name).lower()
        if normalized in dependencies:
            raise ValueError('Duplicate dependency in installation report')
        dependencies[normalized] = version
        if normalized == 'eazyclass-tableparser':
            if item['download_info']['archive_info']['hashes']['sha256'] != wheel_sha256:
                raise ValueError('Installation report refers to another wheel')
    if 'eazyclass-tableparser' not in dependencies:
        raise ValueError('Installation report must include the parser')
    with zipfile.ZipFile(wheel) as archive:
        code = {name: hashlib.sha256(archive.read(name)).hexdigest()
                for name in archive.namelist() if name.endswith('.py')}
    if not code:
        raise ValueError('Wheel has no Python code')
    output.mkdir(parents=True)
    (output / 'INCOMPLETE').write_text('Release preparation has not completed\n')
    for name, checksum in inputs.items():
        if name == 'data/knowledge.sqlite3' or '__pycache__' in Path(name).parts:
            continue
        dest = output / 'runtime' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(resources / name, dest)
        if sha256(dest) != checksum:
            raise ValueError('Resource changed while copying')
    (output / 'seed').mkdir()
    shutil.copyfile(knowledge, output / 'seed/knowledge.sqlite3')
    if sha256(output / 'seed/knowledge.sqlite3') != knowledge_hash:
        raise ValueError('Knowledge seed changed while copying')
    context = output / 'image'
    context.mkdir()
    shutil.copyfile(wheel, context / wheel.name)
    if sha256(context / wheel.name) != wheel_sha256:
        raise ValueError('Wheel changed while copying')
    constraints = '\n'.join(f'{name}=={version}' for name, version in sorted(dependencies.items())) + '\n'
    (context / 'constraints.txt').write_text(constraints, encoding='utf-8', newline='\n')
    (context / 'wheel.sha256').write_text(f'{wheel_sha256}  {wheel.name}\n', encoding='utf-8', newline='\n')
    (context / 'Dockerfile').write_text('''ARG EAZYCLASS_BASE_IMAGE
FROM ${EAZYCLASS_BASE_IMAGE}
USER root
COPY . /opt/tableparser-install/
RUN cd /opt/tableparser-install && sha256sum -c wheel.sha256 \\
    && python -m pip install --no-cache-dir -c constraints.txt ./*.whl \\
    && python -m pip install --no-cache-dir -r constraints.txt \\
    && python -m pip check
''', encoding='utf-8', newline='\n')
    data = dict(format=1, parser_version=dependencies['eazyclass-tableparser'],
        wheel='image/' + wheel.name, knowledge='seed/knowledge.sqlite3', code=code,
        dependencies=dependencies, validation_environment=report['environment'],
        excluded_resource_knowledge_sha256=inputs.get('data/knowledge.sqlite3'))
    data['files'] = inventory(output)
    data['files'].pop('INCOMPLETE')
    manifest = output / 'release.json'
    manifest.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8', newline='\n')
    (output / 'INCOMPLETE').unlink()
    return sha256(manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('wheel', 'wheel-sha256', 'resources', 'knowledge', 'install-report', 'output'):
        parser.add_argument('--' + name, required=True)
    args = vars(parser.parse_args())
    print(build_bundle(**args))


if __name__ == '__main__':
    main()
