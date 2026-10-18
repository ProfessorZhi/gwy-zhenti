"""Synthetic tests for tools/qa/fast10_shards.py.

Fixtures only: no real question text, no image bytes, no credentials. They prove
the guards fire, not that any real paper is correct.

    python3 -I tools/qa/test_fast10_shards.py -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fast10_shards as F  # noqa: E402


def manifest(shards):
    return {
        'schemaVersion': 1,
        'rules': {'maxPapersPerShard': 3},
        'shards': [{'id': sid, 'papers': papers} for sid, papers in shards.items()],
    }


def paper(src, path='省考/X/2026/行测-统考.md'):
    return {'sourceId': src, 'paper': path, 'area': 'X', 'year': 2026, 'variant': '统考'}


def verification(src, slots, verified, remaining, stub, files=10, sha=10, official=False):
    return {
        'sourceId': src, 'realQuestionSlots': slots, 'stemEligible': slots,
        'imageOnlyQuestions': 0, 'stubCount': stub,
        'images': {'files': files, 'shaVerified': sha, 'allVerified': files == sha},
        'mapping': {'basis': 'number-based alignment matched', 'verifiedCount': verified,
                    'remainingMissing': remaining},
        'evidenceLevel': 'single-source-no-independent-qa',
        'officialVerification': official,
    }


def observations(sources, permissions=None):
    return {
        'schemaVersion': 1, 'kind': 'gwy-zhenti-source-observation',
        'permissions': permissions or {'browserProfile': False, 'cookies': False, 'tokens': False},
        'observations': [
            {'paperSourceId': src, 'title': 't', 'subject': 'xingce', 'area': 'X', 'year': 2026,
             'variant': '统考', 'version': 'v1', 'questionCount': 100,
             'contentStatus': 'observed',
             'route': {'kind': 'existing_practice', 'url': 'https://www.fenbi.com/x',
                       'urlObserved': True, 'contentStatus': 'observed', 'questionCount': 100,
                       'imageContentOnly': False, 'evidence': [{'type': 'observed_ui', 'ref': 'r'}]},
             'rights': {'category': 'observed_ui', 'license': None, 'redistribution': 'local_only',
                        'evidence': [{'type': 'observed_ui', 'ref': 'r'}]},
             'images': [{'ref': 'a.png', 'sha256': 'a' * 64, 'sourceUrl': 'https://x/a.png'}]}
            for src in sources
        ],
    }


class ManifestTests(unittest.TestCase):
    def test_duplicate_paper_across_shards_is_rejected(self):
        m = manifest({'a': [paper('1')], 'b': [paper('1')]})
        problems, _, _ = F.validate_manifest(m)
        self.assertTrue(any('appears in' in p for p in problems), problems)

    def test_shard_over_cap_is_rejected(self):
        m = manifest({'a': [paper('1'), paper('2'), paper('3'), paper('4')]})
        problems, _, _ = F.validate_manifest(m)
        self.assertTrue(any('outside 1..3' in p for p in problems), problems)

    def test_a_clean_manifest_passes(self):
        m = manifest({'a': [paper('1'), paper('2')], 'b': [paper('3')]})
        problems, by_source, total = F.validate_manifest(m)
        self.assertEqual(problems, [])
        self.assertEqual(total, 3)
        self.assertEqual(set(by_source), {'1', '2', '3'})


class FingerprintOnlyTests(unittest.TestCase):
    def test_question_text_is_refused(self):
        doc = {'observations': [{'paperSourceId': '1', 'contentHtml': '题干'}]}
        self.assertEqual(F.find_forbidden(doc), '$.observations[0].contentHtml')

    def test_credentials_are_refused(self):
        for key in ('cookie', 'token', 'answer'):
            self.assertEqual(F.find_forbidden({'x': [{key: 'v'}]}), f'$.x[0].{key}', key)

    def test_counts_are_not_text(self):
        doc = {'materials': 5, 'options': 0, 'images': {'files': 31, 'shaVerified': 31}}
        self.assertIsNone(F.find_forbidden(doc))

    def test_permission_block_is_a_declaration_not_a_credential(self):
        doc = {'permissions': {'browserProfile': False, 'cookies': False, 'tokens': False}}
        self.assertIsNone(F.find_forbidden(doc))


class ClassificationTests(unittest.TestCase):
    def classify(self, v, obs=None, route=None):
        return F.classify_paper(paper('1'), obs, v, route)

    def test_clean_paper_is_ready_but_never_auto_accepted(self):
        row = self.classify(verification('1', 100, 100, 0, 0), obs={'questionCount': 100})
        self.assertTrue(row['input_ready'])
        self.assertFalse(row['autoAcceptAllowed'], 'single-source evidence must never self-certify')
        self.assertTrue(any(b['category'] == 'auto_accept' for b in row['blockers']))

    def test_image_byte_conflict_blocks_auto_accept(self):
        row = self.classify(verification('1', 100, 100, 0, 0, files=10, sha=8))
        self.assertEqual(row['categories']['image_conflict'], 2)
        self.assertFalse(row['autoAcceptAllowed'])
        self.assertTrue(any(b['category'] == 'image_conflict' for b in row['blockers']))

    def test_unmeasured_categories_are_blocked_not_zero(self):
        row = self.classify(verification('1', 100, 100, 0, 0))
        for key in ('near', 'weak', 'ambiguous'):
            self.assertIsNone(row['categories'][key], key)
            self.assertTrue(any(b['category'] == key and b['state'] == 'blocked'
                                for b in row['blockers']), key)

    def test_stub_inclusive_and_exclusive_accounting_both_surface(self):
        inclusive = self.classify(verification('1', 100, 88, 12, 12))
        self.assertTrue(inclusive['accounting']['remainingIncludesStubs'])
        exclusive = self.classify(verification('1', 100, 90, 6, 4))
        self.assertFalse(exclusive['accounting']['remainingIncludesStubs'])
        self.assertTrue(exclusive['accounting']['consistent'])

    def test_impossible_accounting_is_flagged(self):
        row = self.classify(verification('1', 100, 90, 6, 1))  # residue 4, stub 1
        self.assertFalse(row['accounting']['consistent'])
        self.assertTrue(any(b['category'] == 'accounting' for b in row['blockers']))

    def test_official_verification_alone_does_not_auto_accept_with_gaps(self):
        row = self.classify(verification('1', 100, 99, 1, 0, official=True))
        self.assertFalse(row['autoAcceptAllowed'])


class EndToEndTests(unittest.TestCase):
    def write(self, tmp, name, doc):
        path = os.path.join(tmp, name)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(doc, fh)
        return path

    def test_four_shards_run_and_sum(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = manifest({'a': [paper('1'), paper('2'), paper('3')],
                          'b': [paper('4'), paper('5'), paper('6')],
                          'c': [paper('7'), paper('8')],
                          'd': [paper('9'), paper('10')]})
            mpath = self.write(tmp, 'm.json', m)
            opath = self.write(tmp, 'o.json', observations([str(i) for i in range(1, 11)]))
            vpath = self.write(tmp, 'v.json', {'containsQuestionText': False, 'papers': [
                verification(str(i), 100, 90, 10, 10) for i in range(1, 11)]})
            rpath = self.write(tmp, 'r.json', {'containsQuestionText': False, 'papers': [
                {'sourceId': str(i), 'route': {'requiresOwnerSession': True},
                 'captureReadyForCredentialFreeCollector': False} for i in range(1, 11)]})
            out = os.path.join(tmp, 'out')
            code = F.main(['--manifest', mpath, '--observations', opath,
                           '--verification', vpath, '--route-stats', rpath,
                           '--workers', '2', '--out', out])
            self.assertEqual(code, 0)
            report = json.load(open(os.path.join(out, 'fast10-report.json'), encoding='utf-8'))
            self.assertEqual(report['papersTotal'], 10)
            self.assertEqual(report['papersWithInput'], 10)
            self.assertEqual(len(report['shards']), 4)
            self.assertEqual(sum(s['totals']['exact'] for s in report['shards']), 900)

    def test_a_batch_claiming_cookies_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            mpath = self.write(tmp, 'm.json', manifest({'a': [paper('1')]}))
            bad = observations(['1'])
            bad['permissions']['cookies'] = True
            opath = self.write(tmp, 'o.json', bad)
            vpath = self.write(tmp, 'v.json', {'papers': [verification('1', 100, 90, 10, 10)]})
            rpath = self.write(tmp, 'r.json', {'papers': [{'sourceId': '1', 'route': {}}]})
            code = F.main(['--manifest', mpath, '--observations', opath,
                           '--verification', vpath, '--route-stats', rpath,
                           '--workers', '1', '--out', os.path.join(tmp, 'out')])
            self.assertEqual(code, 1)

    def test_question_text_in_a_digest_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            mpath = self.write(tmp, 'm.json', manifest({'a': [paper('1')]}))
            opath = self.write(tmp, 'o.json', observations(['1']))
            vpath = self.write(tmp, 'v.json', {'papers': [
                {**verification('1', 100, 90, 10, 10), 'stem': '真实的题干'}]})
            rpath = self.write(tmp, 'r.json', {'papers': [{'sourceId': '1', 'route': {}}]})
            code = F.main(['--manifest', mpath, '--observations', opath,
                           '--verification', vpath, '--route-stats', rpath,
                           '--workers', '1', '--out', os.path.join(tmp, 'out')])
            self.assertEqual(code, 1)


if __name__ == '__main__':
    unittest.main()
