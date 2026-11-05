"""Real PNG/CLI operations: candidates stay unapproved; visible mutations produce diffs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import runpy
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/visual-regression/compare.py'
API = runpy.run_path(str(SCRIPT))


class VisualRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='visual-caller-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.marker = self.root / 'owner.txt'
        self.marker.write_bytes(b'caller keeps exact bytes\x00\xff')
        self.pixels = bytes((20, 60, 100, 255)) * 100
        self.image = API['png_encode'](10, 10, self.pixels)
        (self.root / 'screen.png').write_bytes(self.image)
        self.capture = {'schema_version': 1, 'kind': 'visual-capture',
                        'environment': {'browser': 'synthetic PNG fixture; not browser acceptance', 'os': 'fixture'},
                        'source': {'kind': 'authored-machine-fixture'},
                        'cases': [{'id': 'settings-ready-light', 'screen': 'settings', 'state': 'ready',
                                   'theme': 'light', 'locale': 'ru', 'viewport': {'width': 10, 'height': 10},
                                   'width': 10, 'height': 10, 'image': 'screen.png',
                                   'sha256': hashlib.sha256(self.image).hexdigest()}]}
        self.save('capture.json', self.capture)

    def tearDown(self):
        self.assertEqual(self.marker.read_bytes(), b'caller keeps exact bytes\x00\xff')

    def save(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), 'utf8')
        return path

    def invoke(self, *arguments):
        result = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(SCRIPT), *map(str, arguments)],
                                cwd=self.root, capture_output=True, text=True, encoding='utf8', timeout=30)
        payload = json.loads(result.stdout or result.stderr)
        return result.returncode, payload

    def make_baseline(self, fixture=True):
        code, candidate = self.invoke('candidate', '--capture', 'capture.json', '--output', 'baseline')
        self.assertEqual(code, 1)
        self.assertFalse(candidate['passed'])
        self.assertFalse(candidate['human_review_verified'])
        path = self.root / 'baseline/manifest.json'
        baseline = json.loads(path.read_text('utf8'))
        self.assertEqual(baseline['review_status'], 'awaiting-human-review')
        if fixture:
            baseline['purpose'] = 'machine-fixture'
            path.write_text(json.dumps(baseline), 'utf8')
        return path

    def compare(self, output='comparison', *extra):
        return self.invoke('compare', '--baseline', 'baseline/manifest.json', '--capture', 'capture.json',
                           '--output', output, *extra)

    def mutate(self, positions):
        pixels = bytearray(self.pixels)
        for index in positions:
            pixels[index * 4:index * 4 + 4] = bytes((255, 255, 0, 255))
        image = API['png_encode'](10, 10, bytes(pixels))
        (self.root / 'screen.png').write_bytes(image)
        self.capture['cases'][0]['sha256'] = hashlib.sha256(image).hexdigest()
        self.save('capture.json', self.capture)

    def test_equal_fixture_emits_all_three_images_without_product_approval(self):
        self.make_baseline()
        code, report = self.compare('equal', '--machine-fixture')
        self.assertEqual(code, 0)
        self.assertTrue(report['passed'])
        self.assertFalse(report['product_acceptance'])
        self.assertFalse(report['human_review_verified'])
        folder = self.root / 'equal/settings-ready-light'
        self.assertEqual((folder / 'actual.png').read_bytes(), (folder / 'expected.png').read_bytes())
        self.assertEqual(API['png_decode']((folder / 'diff.png').read_bytes())[:2], (10, 10))

    def test_one_pixel_and_larger_defect_fail_then_restored_capture_passes(self):
        self.make_baseline()
        for name, positions in [('one-pixel', [50]), ('visible-block', range(40, 60))]:
            self.mutate(positions)
            code, report = self.compare(name, '--machine-fixture')
            self.assertEqual(code, 1)
            self.assertFalse(report['passed'])
            self.assertEqual(report['different_pixels'], len(positions))
            image = API['png_decode']((self.root / name / 'settings-ready-light/diff.png').read_bytes())[2]
            self.assertEqual(image[50 * 4:50 * 4 + 4], bytes((255, 0, 130, 255)))
        (self.root / 'screen.png').write_bytes(self.image)
        self.capture['cases'][0]['sha256'] = hashlib.sha256(self.image).hexdigest()
        self.save('capture.json', self.capture)
        self.assertEqual(self.compare('restored', '--machine-fixture')[0], 0)

    def test_approval_json_flag_alone_cannot_authorize_product_or_fixture_mode(self):
        baseline = self.make_baseline(fixture=False)
        value = json.loads(baseline.read_text('utf8'))
        value.update(approved=True, reviewer='invented reviewer', review_status='approved')
        baseline.write_text(json.dumps(value), 'utf8')
        code, report = self.compare()
        self.assertEqual(code, 2)
        self.assertEqual(report['code'], 'externally-reviewed-baseline-pin-required')
        self.assertFalse((self.root / 'comparison').exists())
        self.assertEqual(self.compare('fake-fixture', '--machine-fixture')[0], 2)

    def test_external_pin_binds_exact_bytes_but_is_never_human_authentication(self):
        baseline = self.make_baseline(fixture=False)
        pin = hashlib.sha256(baseline.read_bytes()).hexdigest()
        code, report = self.compare('pinned', '--approved-baseline-sha256', pin)
        self.assertEqual(code, 0)
        self.assertFalse(report['human_review_verified'])
        self.assertFalse(report['product_acceptance'])
        baseline.write_bytes(baseline.read_bytes() + b'\n')
        code, report = self.compare('stale-pin', '--approved-baseline-sha256', pin)
        self.assertEqual((code, report['code']), (2, 'review-pin-mismatch'))

    def test_masks_explain_variation_keep_actions_and_detect_unmasked_pixel(self):
        baseline = self.make_baseline()
        value = json.loads(baseline.read_text('utf8'))
        case = value['cases'][0]
        case['protected_regions'] = [{'x': 0, 'y': 5, 'width': 10, 'height': 5}]
        case['masks'] = [{'x': 0, 'y': 0, 'width': 1, 'height': 1,
                          'reason': 'Synthetic changing clock; no action or error occupies this pixel.'}]
        baseline.write_text(json.dumps(value), 'utf8')
        self.mutate([0])
        code, report = self.compare('masked-clock', '--machine-fixture')
        self.assertEqual(code, 0)
        self.assertEqual(report['cases'][0]['masked_different_pixels'], 1)
        self.mutate([0, 50])
        code, report = self.compare('unmasked-action', '--machine-fixture')
        self.assertEqual(code, 1)
        self.assertEqual(report['different_pixels'], 1)

    def test_unsafe_masks_and_budget_are_refused(self):
        self.make_baseline()
        expected = API['png_decode'](self.image)
        base = {'protected_regions': [{'x': 0, 'y': 5, 'width': 10, 'height': 5}]}
        for entry, reason in [({'x': 0, 'y': 0, 'width': 1, 'height': 1, 'reason': 'hide'}, 'mask-explanation'),
                              ({'x': 0, 'y': 5, 'width': 1, 'height': 1, 'reason': 'Long explanation hiding action'}, 'protected'),
                              ({'x': 0, 'y': 0, 'width': 10, 'height': 2, 'reason': 'Long explanation hiding too much'}, 'ten-percent'),
                              ({'x': -1, 'y': 0, 'width': 1, 'height': 1, 'reason': 'Long explanation outside image'}, 'outside')]:
            with self.subTest(reason=reason), self.assertRaisesRegex(API['Rejected'], reason):
                API['difference'](expected, expected, dict(base, masks=[entry]))
        with self.assertRaisesRegex(API['Rejected'], 'protected-regions'):
            API['difference'](expected, expected, {'masks': [{'x': 0, 'y': 0, 'width': 1, 'height': 1,
                                                             'reason': 'Unprotected synthetic changing region'}]})
        with self.assertRaisesRegex(API['Rejected'], 'budget'):
            API['difference'](expected, expected, {'max_diff_pixels': 101})

    def test_existing_output_never_replaces_owner_files(self):
        self.make_baseline()
        output = self.root / 'existing'
        output.mkdir()
        marker = output / 'owner.txt'
        marker.write_bytes(b'owned output')
        self.assertEqual(self.compare('existing', '--machine-fixture')[0], 2)
        self.assertEqual(marker.read_bytes(), b'owned output')
        self.assertEqual(list(output.iterdir()), [marker])

    def test_missing_baseline_missing_case_source_drift_and_environment_mismatch_refuse(self):
        self.assertEqual(self.compare('missing')[0], 2)
        self.make_baseline()
        (self.root / 'screen.png').write_bytes(self.image + b'extra')
        self.assertEqual(self.compare('drift', '--machine-fixture')[0], 2)
        (self.root / 'screen.png').write_bytes(self.image)
        self.capture['environment']['os'] = 'different renderer'
        self.save('capture.json', self.capture)
        self.assertEqual(self.compare('environment', '--machine-fixture')[0], 2)
        self.capture['environment']['os'] = 'fixture'
        self.capture['cases'][0]['id'] = 'different-case'
        self.save('capture.json', self.capture)
        self.assertEqual(self.compare('matrix', '--machine-fixture')[0], 2)

    def test_absolute_traversal_and_linked_input_refuse(self):
        for image in ('../screen.png', str(self.root / 'screen.png'), 'C:/screen.png', 'folder\\screen.png'):
            with self.subTest(image=image):
                self.capture['cases'][0]['image'] = image
                self.save('capture.json', self.capture)
                self.assertEqual(self.invoke('candidate', '--capture', 'capture.json', '--output', 'bad')[0], 2)
        link = self.root / 'linked'
        destination = self.root / 'real'
        destination.mkdir()
        if os.name == 'nt':
            made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(destination)],
                                  capture_output=True, timeout=10)
            if made.returncode:
                self.skipTest('Windows junction unavailable')
        else:
            link.symlink_to(destination, target_is_directory=True)
        try:
            with self.assertRaisesRegex(API['Rejected'], 'linked-path'):
                API['new_directory'](link / 'report')
            self.assertFalse((destination / 'report').exists())
        finally:
            link.rmdir() if os.name == 'nt' else link.unlink()

    def test_png_crc_inflation_and_unsupported_format_refuse(self):
        damaged = bytearray(self.image)
        damaged[20] ^= 1
        with self.assertRaisesRegex(API['Rejected'], 'crc'):
            API['png_decode'](damaged)
        with self.assertRaises(API['Rejected']):
            API['png_decode'](self.image[:-1])
        with self.assertRaises(API['Rejected']):
            API['png_decode'](self.image + b'extra')
        def chunk(tag, body):
            return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body) & 0xffffffff)
        too_much = (API['SIGNATURE'] + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
                    + chunk(b'IDAT', zlib.compress(b'\0' * 1000)) + chunk(b'IEND', b''))
        with self.assertRaisesRegex(API['Rejected'], 'inflate-size'):
            API['png_decode'](too_much)

    def test_layout_dimension_change_is_a_failed_visual_diff_not_an_approved_budget(self):
        self.make_baseline()
        image = API['png_encode'](10, 11, bytes((20, 60, 100, 255)) * 110)
        (self.root / 'screen.png').write_bytes(image)
        self.capture['cases'][0].update(height=11, sha256=hashlib.sha256(image).hexdigest())
        self.save('capture.json', self.capture)
        code, report = self.compare('height-regression', '--machine-fixture')
        self.assertEqual(code, 1)
        self.assertFalse(report['cases'][0]['dimensions_match'])
        self.assertEqual(report['different_pixels'], 10)
        self.assertEqual(API['png_decode']((self.root / 'height-regression/settings-ready-light/diff.png').read_bytes())[:2], (10, 11))

    def test_rgb_png_all_filter_modes_decode_against_authored_pixels(self):
        def chunk(tag, body):
            return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body) & 0xffffffff)
        # Flat RGB rows make all predictors independently calculable; test every PNG filter.
        for method in range(5):
            rows = []
            for y in range(2):
                values = []
                for i in range(6):
                    left, up, corner = (40 if i >= 3 else 0), (40 if y else 0), (40 if y and i >= 3 else 0)
                    prediction = (0, left, up, (left + up) // 2, left if i >= 3 else up)[method]
                    values.append((40 - prediction) & 255)
                rows.append(bytes([method, *values]))
            image = (API['SIGNATURE'] + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b''))
            with self.subTest(filter=method):
                self.assertEqual(API['png_decode'](image), (2, 2, bytes((40, 40, 40, 255)) * 4))

    def test_color_metadata_cannot_silently_change_rendering_with_equal_rgba(self):
        def chunk(tag, body):
            return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body) & 0xffffffff)
        for tag, data in [(b'gAMA', struct.pack('>I', 45455)), (b'sRGB', b'\0'),
                          (b'tRNS', b'\0' * 6), (b'iCCP', b'profile\0\0' + zlib.compress(b'fixture'))]:
            with self.subTest(chunk=tag), self.assertRaisesRegex(API['Rejected'], 'metadata-unsupported'):
                API['png_decode'](self.image[:33] + chunk(tag, data) + self.image[33:])


if __name__ == '__main__':
    unittest.main()
