"""Apply GitOps-owned dashboard auth fields to an existing Hermes PVC config."""
import copy
import os
from pathlib import Path
import yaml


def migrate(existing, desired):
    if not isinstance(existing, dict) or not isinstance(desired, dict):
        raise ValueError('Hermes configuration must be a mapping')
    result = copy.deepcopy(existing)
    plugins = result.setdefault('plugins', {})
    plugins['enabled'] = [x for x in plugins.get('enabled', []) if x not in ['basic', 'self_hosted', 'self-hosted']] + ['self-hosted']
    plugins['disabled'] = [x for x in plugins.get('disabled', []) if x not in ['basic', 'self_hosted', 'self-hosted']] + ['basic']
    dashboard = result.setdefault('dashboard', {})
    dashboard.pop('basic_auth', None)
    dashboard['public_url'] = desired['dashboard']['public_url']
    oauth = dashboard.setdefault('oauth', {})
    oauth['provider'] = 'self-hosted'
    oauth['self_hosted'] = copy.deepcopy(desired['dashboard']['oauth']['self_hosted'])
    return result


def main():
    path = Path('/opt/data/config.yaml')
    original = yaml.safe_load(path.read_text())
    desired = yaml.safe_load(Path('/config/config.yaml').read_text())
    updated = migrate(original, desired)
    if updated != original:
        temporary = path.with_suffix('.sso.tmp')
        temporary.write_text(yaml.safe_dump(updated, sort_keys=False))
        os.replace(temporary, path)
    print('Hermes dashboard OIDC configuration reconciled.')


if __name__ == '__main__':
    main()
