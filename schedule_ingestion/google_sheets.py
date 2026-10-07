"""Public GViz reader compatible with the local parser's formatted-cell handling."""
import json
import re

import requests


class SheetResponseError(ValueError):
    pass


class SheetTransportError(RuntimeError):
    pass


def decode_rows(text):
    match = re.fullmatch(r'\s*(?:/\*.*?\*/\s*)?google\.visualization\.Query\.setResponse\((.*)\);?\s*',
                         text, flags=re.DOTALL)
    if not match:
        raise SheetResponseError('Invalid GViz response envelope')
    try:
        document = json.loads(match[1])
    except ValueError:
        raise SheetResponseError('Invalid GViz JSON') from None
    if not isinstance(document, dict) or document.get('status') != 'ok':
        raise SheetResponseError('Google did not return a successful sheet response')
    table = document.get('table')
    if not isinstance(table, dict) or not isinstance(table.get('rows'), list):
        raise SheetResponseError('Missing sheet rows')
    result = []
    for row in table['rows']:
        if not isinstance(row, dict) or not isinstance(row.get('c'), list):
            raise SheetResponseError('Invalid sheet row')
        values = []
        for cell in row['c']:
            if cell is None:
                values.append('')
                continue
            if not isinstance(cell, dict):
                raise SheetResponseError('Invalid sheet cell')
            if any(value is not None and not isinstance(value, (str, int, float, bool))
                   for value in (cell.get('f'), cell.get('v'))):
                raise SheetResponseError('Invalid sheet value')
            # Match build_raw_csv_rows from the established local acquisition.
            values.append(str(cell.get('f') or cell.get('v') or '').strip())
        result.append(values)
    return result


def fetch_sheet(spreadsheet_id, gid):
    if not isinstance(spreadsheet_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', spreadsheet_id):
        raise ValueError('Invalid spreadsheet ID')
    if type(gid) is not int or gid < 0:
        raise ValueError('Invalid sheet gid')
    try:
        with requests.get(f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq',
                          params={'tqx': 'out:json', 'gid': gid}, timeout=(10, 30)) as response:
            if response.status_code in (408, 429) or response.status_code >= 500:
                raise SheetTransportError('Temporary sheet fetch failure')
            if response.status_code != 200:
                raise SheetResponseError('Sheet HTTP response was not successful')
            return decode_rows(response.text)
    except requests.RequestException:
        raise SheetTransportError('Sheet connection failed') from None
