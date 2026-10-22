"""Regression checks for resolved installed-module containment."""
from pathlib import Path
import tempfile
import unittest

from clean_install import assert_installed_location


class InstalledLocationTests(unittest.TestCase):
    def test_accepts_same_environment_through_a_parent_alias(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            environment = root / 'real' / 'clean venv'
            environment.mkdir(parents=True)
            module = environment / 'module.py'
            module.touch()
            alias = root / 'alias'
            alias.symlink_to(root / 'real', target_is_directory=True)
            assert_installed_location(module, alias / 'clean venv')
            assert_installed_location(alias / 'clean venv' / 'module.py', environment)

    def test_rejects_external_module_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            environment = root / 'clean venv'
            environment.mkdir()
            outside = root / 'outside.py'
            outside.touch()
            linked = environment / 'linked.py'
            linked.symlink_to(outside)
            for module in (outside, linked):
                with self.assertRaises(AssertionError):
                    assert_installed_location(module, environment)


if __name__ == '__main__':
    unittest.main()
