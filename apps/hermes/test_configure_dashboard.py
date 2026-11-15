"""Persisted Hermes config migration must preserve unrelated user settings."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('migration', Path(__file__).with_name('configure-dashboard.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DashboardMigration(unittest.TestCase):
    def test_existing_pvc_settings_survive_sso_migration(self):
        old = {'model': {'default': 'my-model'}, 'platforms': {'telegram': {'enabled': True}},
               'plugins': {'enabled': ['basic', 'custom-plugin'], 'disabled': ['self-hosted']},
               'dashboard': {'basic_auth': {'password_hash': 'old-test-hash'}, 'chat': {'enabled': True}}}
        desired = {'dashboard': {'public_url': 'https://hermes.example.test', 'oauth': {'self_hosted': {'issuer': 'https://idp.example.test', 'client_id': 'hermes-dashboard'}}}}
        new = module.migrate(old, desired)
        self.assertEqual(new['model'], old['model'])
        self.assertEqual(new['platforms'], old['platforms'])
        self.assertEqual(new['dashboard']['chat'], old['dashboard']['chat'])
        self.assertNotIn('basic_auth', new['dashboard'])
        self.assertEqual(new['plugins']['enabled'], ['custom-plugin', 'self-hosted'])
        self.assertIn('basic', new['plugins']['disabled'])
        self.assertEqual(module.migrate(new, desired), new)
        self.assertIn('basic_auth', old['dashboard'])

    def test_corrupt_config_is_not_replaced_with_defaults(self):
        with self.assertRaises(ValueError):
            module.migrate('invalid-scalar-config', {})


if __name__ == '__main__':
    unittest.main()
