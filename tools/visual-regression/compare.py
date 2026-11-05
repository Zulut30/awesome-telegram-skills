"""Strict, dependency-free PNG comparison; human approval is an external trust input.

Supports the 8-bit RGB/RGBA, non-interlaced PNGs emitted by the browser harness.
It does not infer a reviewer from a JSON field or automatically update baselines.
"""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import sys
import zlib

MAX_PIXELS = 16_777_216
MAX_BYTES = 32 * 1024 * 1024
SIGNATURE = b'\x89PNG\r\n\x1a\n'


class Rejected(ValueError):
    pass


def require(value: bool, reason: str) -> None:
    if not value:
        raise Rejected(reason)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def png_decode(data: bytes) -> tuple[int, int, bytes]:
    require(len(data) <= MAX_BYTES and data.startswith(SIGNATURE), 'unsupported-png')
    offset, compressed, header, ended = 8, bytearray(), None, False
    while offset < len(data):
        require(offset + 12 <= len(data), 'truncated-png')
        length = struct.unpack_from('>I', data, offset)[0]
        tag = data[offset + 4:offset + 8]
        require(offset + length + 12 <= len(data), 'truncated-png')
        value = data[offset + 8:offset + 8 + length]
        crc = struct.unpack_from('>I', data, offset + 8 + length)[0]
        require(zlib.crc32(tag + value) & 0xffffffff == crc, 'png-crc')
        require(header is not None or tag == b'IHDR', 'png-header-first')
        if tag == b'IHDR':
            require(header is None and length == 13, 'png-header')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', value)
            require(0 < width * height <= MAX_PIXELS and width > 0 and height > 0,
                    'png-dimensions')
            require(depth == 8 and color in (2, 6) and (compression, filtering, interlace) == (0, 0, 0),
                    'png-rgb-rgba8-noninterlaced-required')
            header = (width, height, 3 if color == 2 else 4)
        elif tag == b'IDAT':
            compressed.extend(value)
        elif tag == b'IEND':
            require(length == 0 and offset + 12 == len(data), 'png-trailing-data')
            ended = True
            break
        elif tag in (b'tRNS', b'gAMA', b'cHRM', b'iCCP', b'sRGB'):
            # RGBA bytes alone cannot model color-management metadata or tRNS.
            # Browser fixtures here omit these chunks; refuse rather than silently ignore them.
            raise Rejected('png-color-or-transparency-metadata-unsupported')
        else:
            require(tag[0] & 32 != 0, 'unsupported-critical-png-chunk')
        offset += length + 12
    require(header is not None and ended and bool(compressed), 'incomplete-png')
    width, height, channels = header
    stride = width * channels
    expected = (stride + 1) * height
    inflater = zlib.decompressobj()
    raw = inflater.decompress(bytes(compressed), expected + 1)
    require(len(raw) == expected and inflater.eof and not inflater.unused_data
            and not inflater.unconsumed_tail, 'png-inflate-size')
    pixels = bytearray()
    previous = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        method = raw[start]
        require(method <= 4, 'png-filter')
        row = bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride):
            left = row[i - channels] if i >= channels else 0
            up = previous[i]
            corner = previous[i - channels] if i >= channels else 0
            if method == 1:
                prediction = left
            elif method == 2:
                prediction = up
            elif method == 3:
                prediction = (left + up) // 2
            elif method == 4:
                p = left + up - corner
                distances = (abs(p - left), abs(p - up), abs(p - corner))
                prediction = (left, up, corner)[distances.index(min(distances))]
            else:
                prediction = 0
            row[i] = (row[i] + prediction) & 255
        if channels == 4:
            pixels.extend(row)
        else:
            for i in range(0, stride, 3):
                pixels.extend(row[i:i + 3])
                pixels.append(255)
        previous = row
    return width, height, bytes(pixels)


def png_encode(width: int, height: int, pixels: bytes) -> bytes:
    require(0 < width * height <= MAX_PIXELS and len(pixels) == width * height * 4,
            'rgba-dimensions')
    def chunk(tag: bytes, value: bytes) -> bytes:
        return struct.pack('>I', len(value)) + tag + value + struct.pack('>I', zlib.crc32(tag + value) & 0xffffffff)
    raw = b''.join(b'\0' + pixels[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (SIGNATURE + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def no_links(path: Path) -> None:
    for part in (path, *path.parents):
        require(not part.is_symlink() and not getattr(part, 'is_junction', lambda: False)(),
                'linked-path-refused')


def owned_file(root: Path, relative: str) -> Path:
    require(isinstance(relative, str) and '\\' not in relative, 'relative-path-required')
    parts = PurePosixPath(relative)
    require(not parts.is_absolute() and bool(parts.parts) and
            all(p not in ('.', '..') and ':' not in p for p in parts.parts), 'relative-path-required')
    path = root.joinpath(*parts.parts).absolute()
    require(path.is_relative_to(root.absolute()), 'path-outside-manifest')
    no_links(path)
    require(path.is_file(), 'missing-image')
    return path


def load_manifest(path: Path, kind: str) -> tuple[dict, bytes]:
    no_links(path.absolute())
    data = path.read_bytes()
    require(len(data) <= 1024 * 1024, 'manifest-too-large')
    value = json.loads(data)
    require(value.get('schema_version') == 1 and value.get('kind') == kind, 'manifest-kind')
    require(isinstance(value.get('environment'), dict) and bool(value['environment']), 'environment-required')
    cases = value.get('cases')
    require(isinstance(cases, list) and 0 < len(cases) <= 500, 'case-count')
    ids = set()
    for case in cases:
        identity = case.get('id')
        require(isinstance(identity, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', identity) is not None,
                'case-id')
        require(identity not in ids, 'duplicate-case')
        ids.add(identity)
        require(all(isinstance(case.get(k), str) and bool(case[k]) for k in ('screen', 'state', 'theme', 'locale')),
                'case-context-required')
        require(isinstance(case.get('viewport'), dict), 'viewport-required')
        image = owned_file(path.parent, case['image']).read_bytes()
        require(digest(image) == case['sha256'], 'image-sha256')
        width, height, _ = png_decode(image)
        require((width, height) == (case['width'], case['height']), 'image-dimensions')
    return value, data


def new_directory(path: Path) -> None:
    no_links(path.absolute())
    path.mkdir(parents=True, exist_ok=False)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8', newline='\n')


def gallery(path: Path, title: str, rows: list[tuple[str, list[str]]]) -> None:
    cards = []
    for name, images in rows:
        figures = ''.join(f'<figure><a href="{escape(image, quote=True)}">'
                          f'<img loading="lazy" src="{escape(image, quote=True)}" alt="{escape(image, quote=True)}">'
                          f'</a><figcaption>{escape(image)}</figcaption></figure>' for image in images)
        cards.append(f'<section><h2>{escape(name)}</h2><div>{figures}</div></section>')
    html = ('<!doctype html><html lang="ru"><meta charset="utf-8"><title>' + escape(title)
            + '</title><style>body{font:16px system-ui;margin:24px;background:#eee;color:#111}'
              'section{background:white;padding:16px;margin:16px 0}section div{display:flex;gap:16px;flex-wrap:wrap}'
              'figure{margin:0;max-width:30%}img{max-width:100%;border:1px solid #888}'
              'figcaption{overflow-wrap:anywhere}@media(max-width:700px){figure{max-width:100%}}</style>'
            + '<h1>' + escape(title) + '</h1><p>Product acceptance: false. Human review verified: false. '
              'This gallery records images only; viewing or a JSON flag does not create approval.</p>'
            + ''.join(cards) + '</html>')
    path.write_text(html, 'utf8', newline='\n')


def candidate(capture: Path, output: Path) -> dict:
    value, original = load_manifest(capture, 'visual-capture')
    new_directory(output)
    baseline = {'schema_version': 1, 'kind': 'visual-baseline', 'purpose': 'candidate',
                'review_status': 'awaiting-human-review', 'capture_sha256': digest(original),
                'environment': value['environment'], 'source': value.get('source'), 'cases': []}
    for original_case in value['cases']:
        case = dict(original_case, image=original_case['id'] + '.png', masks=[], protected_regions=[], max_diff_pixels=0)
        shutil.copyfile(owned_file(capture.parent, original_case['image']), output / case['image'])
        baseline['cases'].append(case)
    write_json(output / 'manifest.json', baseline)
    gallery(output / 'review.html', 'Baseline candidates: awaiting human review',
            [(case['id'], [case['image']]) for case in baseline['cases']])
    return {'passed': False, 'candidate_created': True, 'human_review_verified': False,
            'code': 'baseline-review-required', 'manifest_sha256': digest((output / 'manifest.json').read_bytes())}


def rectangle(value: dict, width: int, height: int) -> tuple[int, int, int, int]:
    require(isinstance(value, dict), 'rectangle-required')
    coords = tuple(value.get(k) for k in ('x', 'y', 'width', 'height'))
    require(all(type(n) is int for n in coords), 'integer-rectangle-required')
    x, y, w, h = coords
    require(x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= width and y + h <= height,
            'rectangle-outside-image')
    return coords


def overlap(a: tuple, b: tuple) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def difference(expected: tuple, actual: tuple, case: dict) -> tuple[dict, bytes]:
    width, height, old = expected
    actual_width, actual_height, new = actual
    canvas_width, canvas_height = max(width, actual_width), max(height, actual_height)
    require(canvas_width * canvas_height <= MAX_PIXELS, 'diff-canvas-too-large')
    dimensions_match = (width, height) == actual[:2]
    masks, protected = case.get('masks', []), case.get('protected_regions', [])
    require(isinstance(masks, list) and isinstance(protected, list), 'mask-policy-required')
    require(not masks or bool(protected), 'protected-regions-required-for-masks')
    protect = [rectangle(r, width, height) for r in protected]
    mask = bytearray(width * height)
    for entry in masks:
        require(isinstance(entry.get('reason'), str) and len(entry['reason'].strip()) >= 20,
                'mask-explanation-required')
        rect = rectangle(entry, width, height)
        require(not any(overlap(rect, p) for p in protect), 'mask-covers-protected-action')
        x, y, w, h = rect
        for row in range(y, y + h):
            mask[row * width + x:row * width + x + w] = b'\1' * w
    masked = sum(mask)
    require(masked <= width * height // 10, 'mask-exceeds-ten-percent')
    tolerance = case.get('max_diff_pixels', 0)
    require(type(tolerance) is int and 0 <= tolerance <= 100, 'diff-budget-out-of-range')
    diff, count, masked_count = bytearray(), 0, 0
    for y in range(canvas_height):
        for x in range(canvas_width):
            old_present, new_present = x < width and y < height, x < actual_width and y < actual_height
            if not old_present and not new_present:
                diff.extend((0, 0, 0, 0))
                continue
            i, j = y * width + x, y * actual_width + x
            changed = not (old_present and new_present) or old[i * 4:i * 4 + 4] != new[j * 4:j * 4 + 4]
            if old_present and new_present and mask[i]:
                diff.extend((30, 100, 255, 255))
                masked_count += changed
            elif changed:
                diff.extend((255, 0, 130, 255))
                count += 1
            else:
                grey = sum(old[i * 4:i * 4 + 3]) // 3
                diff.extend((grey, grey, grey, 100))
    return {'passed': dimensions_match and count <= tolerance, 'different_pixels': count,
            'dimensions_match': dimensions_match, 'expected_dimensions': [width, height],
            'actual_dimensions': [actual_width, actual_height], 'max_diff_pixels': tolerance,
            'masked_pixels': masked, 'masked_different_pixels': masked_count,
            'algorithm': 'exact RGBA byte comparison; no perceptual/antialias exclusion'}, png_encode(canvas_width, canvas_height, diff)


def compare(baseline: Path, capture: Path, output: Path, pin: str | None, fixture: bool) -> dict:
    expected, baseline_bytes = load_manifest(baseline, 'visual-baseline')
    actual, actual_bytes = load_manifest(capture, 'visual-capture')
    if fixture:
        require(expected.get('purpose') == 'machine-fixture', 'fixture-only-baseline-required')
    else:
        require(pin is not None and re.fullmatch(r'[0-9a-f]{64}', pin) is not None,
                'externally-reviewed-baseline-pin-required')
        require(pin == digest(baseline_bytes), 'review-pin-mismatch')
        require(expected.get('purpose') == 'candidate', 'product-baseline-required')
    require(expected['environment'] == actual['environment'], 'environment-mismatch')
    by_id = {c['id']: c for c in actual['cases']}
    require(set(by_id) == {c['id'] for c in expected['cases']}, 'case-matrix-mismatch')
    new_directory(output)
    rows = []
    for case in expected['cases']:
        other = by_id[case['id']]
        require(all(case[key] == other[key] for key in ('screen', 'state', 'theme', 'locale', 'viewport')),
                'case-context-mismatch')
        old_path = owned_file(baseline.parent, case['image'])
        new_path = owned_file(capture.parent, other['image'])
        row, diff = difference(png_decode(old_path.read_bytes()), png_decode(new_path.read_bytes()), case)
        folder = output / case['id']
        folder.mkdir()
        shutil.copyfile(old_path, folder / 'expected.png')
        shutil.copyfile(new_path, folder / 'actual.png')
        (folder / 'diff.png').write_bytes(diff)
        rows.append(dict(row, id=case['id'], expected_sha256=case['sha256'], actual_sha256=other['sha256'],
                         diff_sha256=digest(diff)))
    passed = all(row['passed'] for row in rows)
    report = {'schema_version': 1, 'kind': 'visual-comparison', 'passed': passed,
              'product_acceptance': False, 'human_review_verified': False,
              'review_basis': 'machine-fixture-only' if fixture else 'caller-supplied external baseline pin; reviewer identity not authenticated',
              'baseline_sha256': digest(baseline_bytes), 'capture_sha256': digest(actual_bytes),
              'cases': rows, 'case_count': len(rows), 'different_pixels': sum(r['different_pixels'] for r in rows),
              'limits': ['Pixel comparison does not prove beauty, accessibility, actions, native clients or real devices.',
                         'A JSON approval flag is never consulted. The caller must obtain a reviewed baseline pin through its own trusted review process.']}
    write_json(output / 'report.json', report)
    gallery(output / 'review.html', 'Visual comparison: review expected / actual / diff',
            [(row['id'], [row['id'] + '/' + name + '.png' for name in ('expected', 'actual', 'diff')])
             for row in rows])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    make = commands.add_parser('candidate')
    make.add_argument('--capture', type=Path, required=True)
    make.add_argument('--output', type=Path, required=True)
    check = commands.add_parser('compare')
    check.add_argument('--baseline', type=Path, required=True)
    check.add_argument('--capture', type=Path, required=True)
    check.add_argument('--output', type=Path, required=True)
    check.add_argument('--approved-baseline-sha256')
    check.add_argument('--machine-fixture', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'candidate':
            result = candidate(args.capture.absolute(), args.output.absolute())
        else:
            result = compare(args.baseline.absolute(), args.capture.absolute(), args.output.absolute(),
                             args.approved_baseline_sha256, args.machine_fixture)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['passed'] else 1
    except (ValueError, OSError, KeyError, TypeError, zlib.error) as error:
        code = str(error) if isinstance(error, Rejected) else 'visual-input-or-output-rejected'
        print(json.dumps({'passed': False, 'code': code}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
