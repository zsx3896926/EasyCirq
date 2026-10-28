import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('minimum_python_selftest', ROOT/'easycirq/scripts/skill_selftest.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class RecursiveCompileTests(unittest.TestCase):
    def test_nested_syntax_failure_cannot_hide_behind_valid_root_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'scripts/nested').mkdir(parents=True)
            (root/'scripts/entry.py').write_text('x = 1\n')
            (root/'scripts/nested/adapters.py').write_text('def broken(:\n')
            result=m.check_python_compile(root)
            self.assertEqual(result['status'],'FAIL')
            self.assertIn('adapters.py',str(result))

if __name__=='__main__':unittest.main()
