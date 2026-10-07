"""Generate TypeScript types, runtime decoders and typed calls of a Mini App backend from its OpenAPI contract.

    python scripts/build_openapi_types.py           # write examples/shop/frontend/src/api-types.ts
    python scripts/build_openapi_types.py --check   # fail when the module is stale

Supported schema keywords: type (string, integer, number, boolean, object, array), enum, properties, required,
additionalProperties: false, items, $ref to #/components/schemas and description. Anything else is refused,
so a constraint the client would silently ignore cannot enter the contract.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'examples/shop/openapi.json'
OUTPUT = ROOT / 'examples/shop/frontend/src/api-types.ts'
KEYWORDS = {'type', 'enum', 'properties', 'required', 'additionalProperties', 'items', '$ref', 'description'}
TYPES = {'string': 'string', 'integer': 'number', 'number': 'number', 'boolean': 'boolean'}
METHODS = ('get', 'post', 'put', 'patch', 'delete')
NAME = re.compile(r'[A-Z][A-Za-z0-9]*')


class ContractError(ValueError):
    """The contract uses something the generator cannot turn into checked client code."""


def reference(schema: dict, schemas: dict) -> str:
    target = schema['$ref']
    match = re.fullmatch(r'#/components/schemas/([A-Za-z0-9]+)', target)
    if not match or match.group(1) not in schemas:
        raise ContractError(f'Unknown reference {target}')
    return match.group(1)


def compact(schema: dict, schemas: dict, where: str) -> dict:
    """The subset of a schema the generated decoder enforces, after checking that nothing else is used."""
    unknown = set(schema) - KEYWORDS
    if unknown:
        raise ContractError(f'{where}: unsupported keywords {sorted(unknown)}')
    if '$ref' in schema:
        if set(schema) - {'$ref', 'description'}:
            raise ContractError(f'{where}: $ref cannot be combined with other keywords')
        return {'ref': reference(schema, schemas)}
    kind = schema.get('type')
    if kind not in (*TYPES, 'object', 'array'):
        raise ContractError(f'{where}: type must be one of string, integer, number, boolean, object, array')
    result: dict = {'type': kind}
    if 'enum' in schema:
        if kind != 'string' or not schema['enum'] or not all(isinstance(v, str) for v in schema['enum']):
            raise ContractError(f'{where}: enum must list strings of a string schema')
        result['enum'] = schema['enum']
    if kind == 'object':
        if schema.get('additionalProperties') is not False:
            raise ContractError(f'{where}: objects must set additionalProperties: false')
        properties = schema.get('properties', {})
        required = schema.get('required', [])
        if set(required) - set(properties):
            raise ContractError(f'{where}: required names a missing property')
        result['properties'] = {name: compact(value, schemas, f'{where}.{name}') for name, value in properties.items()}
        result['required'] = required
    elif kind == 'array':
        if 'items' not in schema:
            raise ContractError(f'{where}: arrays need items')
        result['items'] = compact(schema['items'], schemas, f'{where}[]')
    elif {'properties', 'required', 'items', 'additionalProperties'} & set(schema):
        raise ContractError(f'{where}: object or array keywords on a {kind}')
    return result


def typescript(schema: dict, schemas: dict, indent: str = '') -> str:
    if '$ref' in schema:
        return reference(schema, schemas)
    kind = schema['type']
    if 'enum' in schema:
        return ' | '.join("'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'" for value in schema['enum'])
    if kind == 'array':
        item = typescript(schema['items'], schemas, indent)
        return f'readonly ({item})[]' if ' | ' in item else f'readonly {item}[]'
    if kind == 'object':
        properties = schema.get('properties', {})
        if not properties:
            return 'Record<string, never>'
        lines = ['{']
        for name, value in properties.items():
            if value.get('description'):
                lines.append(f'{indent}  /** {value["description"]} */')
            optional = '' if name in schema.get('required', []) else '?'
            lines.append(f'{indent}  readonly {name}{optional}: {typescript(value, schemas, indent + "  ")};')
        lines.append(indent + '}')
        return '\n'.join(lines)
    return TYPES[kind]


def response_schema(operation: dict, where: str, schemas: dict) -> str:
    success = operation.get('responses', {}).get('200')
    try:
        schema = success['content']['application/json']['schema']
    except (KeyError, TypeError):
        raise ContractError(f'{where}: a 200 application/json response is required') from None
    return reference(schema, schemas)


def render(spec: dict, source: str) -> str:
    if not str(spec.get('openapi', '')).startswith('3.1'):
        raise ContractError('OpenAPI 3.1 is required')
    schemas = spec['components']['schemas']
    for name in schemas:
        if not NAME.fullmatch(name):
            raise ContractError(f'Schema name {name} must be PascalCase')
    compacted = {name: compact(schema, schemas, name) for name, schema in schemas.items()}
    lines = [
        f'// Generated by scripts/build_openapi_types.py from {source}. Do not edit: change the contract.',
        '// Every schema has a type and a runtime decoder; every operation has its method, path, parameters,',
        '// body and response, so a contract change that the client does not follow fails type checking.',
        "import type {ApiClient, RequestOptions} from '@awesome-telegram/patterns';",
        '',
    ]
    for name, schema in schemas.items():
        if schema.get('description'):
            lines.append(f'/** {schema["description"]} */')
        body = typescript(schema, schemas)
        if body.startswith('{'):
            lines.append(f'export interface {name} {body}')
        else:
            lines.append(f'export type {name} = {body};')
    lines += [
        '',
        "type Schema = {readonly ref: string} | {readonly type: 'string' | 'integer' | 'number' | 'boolean' | 'object' | 'array';",
        '  readonly enum?: readonly string[]; readonly properties?: Readonly<Record<string, Schema>>;',
        '  readonly required?: readonly string[]; readonly items?: Schema};',
        f'const schemas: Readonly<Record<string, Schema>> = {json.dumps(compacted, ensure_ascii=False, separators=(",", ":"))};',
        '',
        '/** Throws with the JSON path of the first value that breaks the contract. */',
        'function check(schema: Schema, value: unknown, at: string): void {',
        "  if ('ref' in schema) return check(schemas[schema.ref]!, value, at);",
        "  const fail = (expected: string): never => { throw new TypeError(`${at}: expected ${expected}`); };",
        '  switch (schema.type) {',
        "    case 'string': if (typeof value !== 'string' || (schema.enum && !schema.enum.includes(value))) fail(schema.enum ? schema.enum.join(' | ') : 'string'); return;",
        "    case 'integer': if (!Number.isSafeInteger(value)) fail('integer'); return;",
        "    case 'number': if (typeof value !== 'number' || !Number.isFinite(value)) fail('number'); return;",
        "    case 'boolean': if (typeof value !== 'boolean') fail('boolean'); return;",
        "    case 'array': if (!Array.isArray(value)) fail('array'); (value as unknown[]).forEach((item, index) => check(schema.items!, item, `${at}[${index}]`)); return;",
        '    case \'object\': {',
        "      if (!value || typeof value !== 'object' || Array.isArray(value)) fail('object');",
        '      const record = value as Record<string, unknown>, properties = schema.properties ?? {};',
        '      for (const name of Object.keys(record)) if (!(name in properties)) fail(`no property ${name}`);',
        "      for (const name of schema.required ?? []) if (!(name in record)) fail(`property ${name}`);",
        '      for (const [name, property] of Object.entries(properties)) if (name in record) check(property, record[name], `${at}.${name}`);',
        '    }',
        '  }',
        '}',
        '',
        '/** Runtime decoders: the value is returned unchanged after a full check against the contract. */',
        'export const decode = {',
    ]
    for name in schemas:
        lines.append(f"  {name}: (value: unknown): {name} => {{ check({{ref: '{name}'}}, value, '{name}'); return value as {name}; }},")
    lines += ['} as const;', '', '/** Every operation of the contract, keyed by operationId. */', 'export interface ApiOperations {']
    table = []
    for path, item in spec['paths'].items():
        for method in METHODS:
            if method not in item:
                continue
            operation = item[method]
            where = f'{method.upper()} {path}'
            operation_id = operation.get('operationId')
            if not isinstance(operation_id, str) or not re.fullmatch(r'[a-z][A-Za-z0-9]*', operation_id):
                raise ContractError(f'{where}: camelCase operationId required')
            names = re.findall(r'\{(\w+)\}', path)
            declared = [p['name'] for p in operation.get('parameters', []) if p.get('in') == 'path']
            if declared != names or any(p.get('schema') != {'type': 'string'} for p in operation.get('parameters', [])):
                raise ContractError(f'{where}: declare every path parameter as a string, in path order')
            params = '{' + ' '.join(f'readonly {name}: string;' for name in names) + '}' if names else 'Record<string, never>'
            body = 'undefined'
            if 'requestBody' in operation:
                body = reference(operation['requestBody']['content']['application/json']['schema'], schemas)
            response = response_schema(operation, where, schemas)
            lines.append(f"  {operation_id}: {{readonly method: '{method.upper()}'; readonly path: '{path}'; readonly params: {params}; "
                         f'readonly body: {body}; readonly response: {response}}};')
            table.append((operation_id, method.upper(), path, response))
    if len({row[0] for row in table}) != len(table):
        raise ContractError('operationId values must be unique')
    lines += ['}', 'export type ApiOperation = keyof ApiOperations;', '', 'export const operations = {']
    for operation_id, method, path, response in table:
        lines.append(f"  {operation_id}: {{method: '{method}', path: '{path}', response: '{response}'}},")
    lines += [
        '} as const satisfies {readonly [K in ApiOperation]: {readonly method: ApiOperations[K][\'method\']; readonly path: ApiOperations[K][\'path\'];',
        '  readonly response: keyof typeof decode}};',
        '',
        '/** Path with every {name} replaced by its URL-encoded parameter. */',
        'export function apiPath<K extends ApiOperation>(operation: K, params: ApiOperations[K][\'params\']): string {',
        '  return operations[operation].path.replace(/\\{(\\w+)\\}/g, (_, name: string) => {',
        '    const value = (params as Readonly<Record<string, string>>)[name];',
        "    if (typeof value !== 'string' || !value) throw new TypeError(`${operation}: path parameter ${name} is required`);",
        '    return encodeURIComponent(value);',
        '  });',
        '}',
        '',
        "type Input<K extends ApiOperation> = (ApiOperations[K]['params'] extends Record<string, never> ? {readonly params?: undefined}",
        "  : {readonly params: ApiOperations[K]['params']}) & (ApiOperations[K]['body'] extends undefined ? {readonly body?: undefined}",
        "  : {readonly body: ApiOperations[K]['body']}) & Omit<RequestOptions, 'method' | 'body'>;",
        '',
        '/** Calls an operation through ApiClient: method and path from the contract, the response decoded against it. */',
        'export function callApi<K extends ApiOperation>(client: ApiClient, operation: K, ...[input]: Record<string, never> extends Input<K> ? [Input<K>?] : [Input<K>]):',
        "    Promise<ApiOperations[K]['response']> {",
        '  const {params, body, ...options} = (input ?? {}) as {params?: Readonly<Record<string, string>>; body?: unknown} & Omit<RequestOptions, \'method\' | \'body\'>;',
        '  const spec = operations[operation];',
        '  const decoder = decode[spec.response] as (value: unknown) => ApiOperations[K][\'response\'];',
        "  return client.request(apiPath(operation, (params ?? {}) as ApiOperations[K]['params']), decoder,",
        '    {...options, method: spec.method, ...(body === undefined ? {} : {body})});',
        '}',
        '',
    ]
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', help='fail instead of writing when the module is stale')
    args = parser.parse_args()
    try:
        content = render(json.loads(SPEC.read_text(encoding='utf-8')), SPEC.relative_to(ROOT).as_posix())
    except ContractError as error:
        sys.stderr.write(f'{SPEC.relative_to(ROOT)}: {error}\n')
        return 1
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding='utf-8') != content:
            sys.stderr.write(f'{OUTPUT.relative_to(ROOT)} is stale; run python scripts/build_openapi_types.py\n')
            return 1
    else:
        OUTPUT.write_text(content, encoding='utf-8', newline='\n')
    print(json.dumps({'passed': True, 'check': args.check, 'output': OUTPUT.relative_to(ROOT).as_posix()}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
