"""Guard the current collector's evidence selection and quiet-load gate."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from owner_state import collect


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.patches = [patch.object(collect, 'FOLDER', self.folder),
                        patch.object(collect, 'STATE', {})]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_selected_evidence_defines_the_inputs(self):
        report = json.loads((collect.ROOT/'owner_state/evidence.json').read_text())['reports']['collect']
        cases = json.loads((collect.ROOT/report/'report.json').read_text())['cases']
        def metadata(variant, mode):
            return None, None, None, cases[f'{variant}/{mode}']['sha256']
        with patch.object(collect.run, 'case_metadata', side_effect=metadata):
            self.assertEqual(set(collect.measured_inputs()), {'cse_dce/direct', 'cse_dce/rlp', 'cse_dce/ssz'})
        with patch.object(collect.run, 'case_metadata', return_value=(None,None,None,{})):
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                collect.measured_inputs()

    def preflight(self, readings):
        values = iter(readings)
        current = None
        def probe(argv, **kwargs):
            nonlocal current
            if argv[0]=='top':
                current=next(values)
                text=f'CPU usage: 1% user, 1% sys, {current[0]}% idle'
            elif argv==['pmset','-g','batt']:
                text="Now drawing from 'AC Power'" if current[1] else "Now drawing from 'Battery Power'"
            else:
                text='recorded probe'
            return SimpleNamespace(stdout=text, returncode=0)
        with patch.object(collect.time, 'sleep'), patch.object(collect.subprocess, 'run', side_effect=probe):
            collect.preflight()

    def test_quiet_checks_must_be_consecutive_and_on_ac(self):
        self.preflight([(95,True),(95,False),(95,True),(89,True),(90,True),(91,True),(92,True)])
        rows=json.loads((self.folder/'preflight.json').read_text())
        self.assertEqual([row['quiet_streak'] for row in rows], [1,0,1,0,1,2,3])
        self.assertEqual(collect.STATE['status'], 'collecting')

    def test_failed_preflight_retains_every_reading(self):
        with self.assertRaisesRegex(RuntimeError, 'no timing batch started'):
            self.preflight([(89,True)]*12)
        self.assertEqual(len(json.loads((self.folder/'preflight.json').read_text())),12)
        self.assertNotEqual(collect.STATE['status'], 'collecting')


if __name__=='__main__':
    unittest.main()
