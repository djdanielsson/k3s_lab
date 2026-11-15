"""Check native CLI orchestration without a shell or live cluster."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location('forgejo_sso', Path(__file__).resolve().parents[1] / 'configure-sso.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ForgejoSSOJob(unittest.TestCase):
    def configure(self, listing, update_code=0):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"issuer":"https://sso.tail7f3c08.ts.net/realms/lab"}'
        calls = []
        def native(command, **kwargs):
            self.assertIsInstance(command, list)
            self.assertFalse(kwargs.get('shell', False))
            self.assertEqual(command[0], '/tools/gitea')
            calls.append(command)
            return SimpleNamespace(returncode=0 if command[-1] == 'list' else update_code, stdout=listing)
        with patch.object(module.urllib.request, 'urlopen', return_value=response), patch.object(module.Path, 'read_text', return_value='separate client secret'), patch.object(module.subprocess, 'run', side_effect=native):
            module.main()
        return calls

    def test_creates_missing_oidc_source_with_native_cli(self):
        calls = self.configure('ID Name Type Enabled\n')
        self.assertIn('add-oauth', calls[1])
        self.assertNotIn('update-oauth', calls[1])
        self.assertIn('separate client secret', calls[1])

    def test_updates_existing_source_without_creating_duplicate(self):
        calls = self.configure('ID Name Type Enabled\n7 lab-sso OAuth2 true\n')
        self.assertIn('update-oauth', calls[1])
        index = calls[1].index('--id')
        self.assertEqual(calls[1][index + 1], '7')
        self.assertNotIn('add-oauth', calls[1])

    def test_failed_cli_write_does_not_report_success(self):
        with self.assertRaisesRegex(RuntimeError, 'configuration failed'):
            self.configure('ID Name Type Enabled\n', update_code=1)

    def test_duplicate_sources_stop_without_writing(self):
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous'):
            self.configure('7 lab-sso OAuth2 true\n8 lab-sso OAuth2 true\n')


if __name__ == '__main__':
    unittest.main()
