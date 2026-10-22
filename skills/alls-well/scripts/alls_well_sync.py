#!/usr/bin/env python3
"""Keep a team's All's Well monitors and alert contacts in step with alls-well.json.

    python3 alls_well_sync.py validate            # check the manifest; no network
    python3 alls_well_sync.py plan                # show what apply would change
    python3 alls_well_sync.py plan --check        # exit 2 if anything would change (CI)
    python3 alls_well_sync.py apply               # create and update
    python3 alls_well_sync.py apply --prune       # also delete this project's unlisted monitors
    python3 alls_well_sync.py apply --env-file .alls-well.env   # write heartbeat ping URLs there (ignored by git)

Reads ALLS_WELL_TOKEN (a team API token). The instance is ALLS_WELL_URL,
else the manifest's "url", else https://alls-well.io. Monitors are matched by name, prefixed with the
manifest's "project", so only this project's monitors are ever changed or
pruned. Contacts are matched by name and never deleted. Strings may use
${ENV_VAR}, so secrets such as webhook URLs stay out of the repository.

Python 3.9 or later, standard library only. Exit codes: 0 done, 1 error,
2 changes pending (with --check).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = 'https://alls-well.io'
MONITOR_TYPES = ('http', 'ssl', 'heartbeat', 'keyword', 'tcp', 'icmp')
INTERVALS = (1, 5, 15, 30, 60)
HTTP_METHODS = ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE')
CONTACT_CONFIG = {
    'email': ('email',),
    'slack': ('webhook_url',),
    'discord': ('webhook_url',),
    'webhook': ('url',),
    'telegram': ('bot_token', 'chat_id'),
}
MONITOR_FIELDS = (
    'url', 'check_interval_minutes', 'check_interval_seconds', 'is_active', 'http_method',
    'expected_status_codes', 'expected_keyword', 'port', 'request_timeout_seconds',
    'request_headers', 'username', 'ssl_expiry_warning_days',
)
ENV_PATTERN = re.compile(r'\$\{([A-Z_][A-Z0-9_]*)\}')


class SyncError(Exception):
    """A problem the user must fix; printed without a traceback."""


# ---------------------------------------------------------------- manifest

def load_manifest(path: str) -> dict:
    try:
        with open(path, encoding='utf-8') as handle:
            manifest = json.load(handle)
    except FileNotFoundError:
        raise SyncError(f'{path} not found. Create it first (see references/manifest.md).')
    except json.JSONDecodeError as error:
        raise SyncError(f'{path} is not valid JSON: {error}')

    problems = validate_manifest(manifest)
    if problems:
        raise SyncError(f'{path} is invalid:\n' + '\n'.join(f'  - {p}' for p in problems))

    return manifest


def validate_manifest(manifest: object) -> list[str]:
    """Every problem with the manifest's shape, without touching the network."""
    if not isinstance(manifest, dict):
        return ['the manifest must be a JSON object']

    problems = []
    project = manifest.get('project')
    if not isinstance(project, str) or not project.strip():
        problems.append('"project" is required: a short name that prefixes every monitor, such as "Northwind shop"')
    if 'url' in manifest and not (isinstance(manifest['url'], str) and re.match(r'^https?://[^/\s]+/?$', manifest['url'])):
        problems.append('"url" must be the All\'s Well instance, such as https://alls-well.io')

    contact_names = set()
    for index, contact in enumerate(manifest.get('contacts', [])):
        where = f'contacts[{index}]'
        if not isinstance(contact, dict):
            problems.append(f'{where} must be an object')
            continue
        name, kind, config = contact.get('name'), contact.get('type'), contact.get('config')
        if not isinstance(name, str) or not name:
            problems.append(f'{where}.name is required')
        elif name in contact_names:
            problems.append(f'{where}.name "{name}" is used twice')
        else:
            contact_names.add(name)
        if kind not in CONTACT_CONFIG:
            problems.append(f'{where}.type must be one of {", ".join(CONTACT_CONFIG)}')
        elif not isinstance(config, dict):
            problems.append(f'{where}.config is required: {{{", ".join(CONTACT_CONFIG[kind])}}}')
        else:
            for key in CONTACT_CONFIG[kind]:
                if not config.get(key):
                    problems.append(f'{where}.config.{key} is required for a {kind} contact')
            for key in config:
                if key not in CONTACT_CONFIG[kind]:
                    problems.append(f'{where}.config.{key} is not used by a {kind} contact (it needs {", ".join(CONTACT_CONFIG[kind])})')
        for flag in ('notify_on_down', 'notify_on_recovery'):
            if flag in contact and not isinstance(contact[flag], bool):
                problems.append(f'{where}.{flag} must be true or false')

    names = set()
    monitors = manifest.get('monitors')
    if not isinstance(monitors, list) or not monitors:
        problems.append('"monitors" must list at least one monitor')
        monitors = []
    for index, monitor in enumerate(monitors):
        where = f'monitors[{index}]'
        if not isinstance(monitor, dict):
            problems.append(f'{where} must be an object')
            continue
        name, kind = monitor.get('name'), monitor.get('type')
        if not isinstance(name, str) or not name:
            problems.append(f'{where}.name is required')
        elif name in names:
            problems.append(f'{where}.name "{name}" is used twice')
        else:
            names.add(name)
        if kind not in MONITOR_TYPES:
            problems.append(f'{where}.type must be one of {", ".join(MONITOR_TYPES)}')
            continue
        url = monitor.get('url')
        if kind == 'heartbeat':
            if url:
                problems.append(f'{where}.url must be left out: a heartbeat monitor is pinged, not checked')
        elif not isinstance(url, str) or not re.match(r'^https?://[^/\s]+', url) and not ENV_PATTERN.search(url):
            problems.append(f'{where}.url must be a full URL such as https://shop.example.com (tcp and icmp use only its host)')
        if kind == 'keyword' and not monitor.get('expected_keyword'):
            problems.append(f'{where}.expected_keyword is required for a keyword monitor')
        if kind == 'tcp' and not isinstance(monitor.get('port'), int):
            problems.append(f'{where}.port is required for a tcp monitor')
        minutes = monitor.get('check_interval_minutes', 5)
        if minutes not in INTERVALS:
            problems.append(f'{where}.check_interval_minutes must be one of {", ".join(map(str, INTERVALS))}')
        seconds = monitor.get('check_interval_seconds')
        if seconds is not None and (not isinstance(seconds, int) or seconds < 30):
            problems.append(f'{where}.check_interval_seconds must be a whole number of seconds, 30 or more')
        if 'http_method' in monitor and monitor['http_method'] not in HTTP_METHODS:
            problems.append(f'{where}.http_method must be one of {", ".join(HTTP_METHODS)}')
        codes = monitor.get('expected_status_codes')
        if codes is not None and (not isinstance(codes, list) or not codes or not all(isinstance(c, int) and 100 <= c <= 599 for c in codes)):
            problems.append(f'{where}.expected_status_codes must be a list of HTTP status codes')
        for field in monitor:
            if field not in MONITOR_FIELDS + ('name', 'type', 'notify', 'password'):
                problems.append(f'{where}.{field} is not a monitor field')

    notify = manifest.get('notify', [])
    for index, monitor in enumerate(monitors):
        if not isinstance(monitor, dict):
            continue
        # A monitor with no contacts alerts every contact on the team, so that has to be said with "notify": [].
        if 'notify' not in monitor and 'notify' not in manifest:
            problems.append(f'monitors[{index}] ("{monitor.get("name")}") alerts nobody: set a top-level "notify" '
                            'or the monitor\'s own, or "notify": [] if nobody should be alerted')
        for contact in monitor.get('notify', notify):
            if not isinstance(contact, str):
                problems.append(f'monitors[{index}].notify must list contact names')

    return problems


def interpolate(value: object, missing: set) -> object:
    """Replace ${VAR} in every string with the environment variable's value."""
    if isinstance(value, str):
        def replace(match: re.Match) -> str:
            if match.group(1) not in os.environ:
                missing.add(match.group(1))
                return match.group(0)
            return os.environ[match.group(1)]

        return ENV_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [interpolate(item, missing) for item in value]
    if isinstance(value, dict):
        return {key: interpolate(item, missing) for key, item in value.items()}
    return value


def env_name(monitor_name: str) -> str:
    return 'ALLS_WELL_PING_' + re.sub(r'[^A-Z0-9]+', '_', monitor_name.upper()).strip('_')


# ---------------------------------------------------------------- API client

class Api:
    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip('/') + '/api/v1'
        self.token = token

    def request(self, method: str, path: str, body: object = None, retry: bool = True) -> object:
        url = path if path.startswith('http') else self.base + path
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': f'Bearer {self.token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'alls-well-sync/1.0',
        })
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            if error.code == 429 and retry:
                wait = min(int(error.headers.get('Retry-After', '5')), 60)
                print(f'  rate limited; waiting {wait}s', file=sys.stderr)
                time.sleep(wait)
                return self.request(method, path, body, retry=False)
            raise SyncError(describe_problem(error, method, url))
        except urllib.error.URLError as error:
            raise SyncError(f'{method} {url} failed: {error.reason}. Check ALLS_WELL_URL.')

    def monitors(self) -> list[dict]:
        found, url = [], '/monitors?per_page=100'
        while url:
            page = self.request('GET', url)
            found.extend(page['data'])
            url = page['links']['next']
        return found

    def contacts(self) -> list[dict]:
        return self.request('GET', '/notification-contacts')['data']

    def team(self) -> dict:
        return self.request('GET', '/team')['data']


def describe_problem(error: urllib.error.HTTPError, method: str, url: str) -> str:
    try:
        problem = json.loads(error.read() or b'{}')
    except json.JSONDecodeError:
        problem = {}

    lines = [f'{method} {url} answered {error.code} {problem.get("title", error.reason)}']
    if problem.get('detail'):
        lines.append(f'  {problem["detail"]}')
    for field, messages in (problem.get('errors') or {}).items():
        lines.append(f'  {field}: {" ".join(messages)}')
    if error.code == 401:
        lines.append('  The token is missing, wrong or revoked. Create one in Settings, API tokens and export ALLS_WELL_TOKEN.')
    elif error.code == 403:
        lines.append('  The token may not do this: it needs an Owner or Admin of the team.')
    elif error.code == 402:
        lines.append(f'  The plan ({problem.get("plan", "?")}) allows {problem.get("max_monitors", "?")} monitors. '
                     'Remove monitors from the manifest or upgrade the plan.')
    return '\n'.join(lines)


# ---------------------------------------------------------------- planning

def desired_monitor(project: str, monitor: dict, default_notify: list[str]) -> dict:
    wanted = {field: monitor[field] for field in MONITOR_FIELDS if field in monitor}
    wanted.setdefault('check_interval_minutes', 5)
    wanted['name'] = f'{project}: {monitor["name"]}'
    wanted['type'] = monitor['type']
    wanted['notify'] = monitor.get('notify', default_notify)
    if 'password' in monitor:
        wanted['password'] = monitor['password']
    return wanted


def plan_changes(manifest: dict, remote_monitors: list[dict], remote_contacts: list[dict], prune: bool) -> list[dict]:
    project = manifest['project'].strip()
    prefix = f'{project}: '
    actions = []

    by_name = {contact['name']: contact for contact in remote_contacts}
    for contact in manifest.get('contacts', []):
        wanted = {
            'name': contact['name'],
            'type': contact['type'],
            'config': contact['config'],
            'notify_on_down': contact.get('notify_on_down', True),
            'notify_on_recovery': contact.get('notify_on_recovery', True),
        }
        existing = by_name.get(contact['name'])
        if existing is None:
            actions.append({'action': 'create', 'kind': 'contact', 'name': contact['name'], 'body': wanted})
            continue
        if existing['type'] != contact['type']:
            raise SyncError(f'Contact "{contact["name"]}" exists as {existing["type"]}, not {contact["type"]}. '
                            'A contact\'s type can\'t change: rename one of them.')
        changes = {key: value for key, value in wanted.items()
                   if key not in ('name', 'type') and existing.get(key) != value}
        if changes:
            actions.append({'action': 'update', 'kind': 'contact', 'name': contact['name'], 'id': existing['id'],
                            'body': changes, 'before': {key: existing.get(key) for key in changes}})

    known_contacts = set(by_name) | {contact['name'] for contact in manifest.get('contacts', [])}
    remote = {monitor['name']: monitor for monitor in remote_monitors if monitor['name'].startswith(prefix)}
    default_notify = manifest.get('notify', [])

    for monitor in manifest['monitors']:
        wanted = desired_monitor(project, monitor, default_notify)
        unknown = [name for name in wanted['notify'] if name not in known_contacts]
        if unknown:
            raise SyncError(f'Monitor "{monitor["name"]}" notifies {", ".join(unknown)}, which is neither in "contacts" '
                            'nor an existing contact of the team.')

        existing = remote.pop(wanted['name'], None)
        if existing is None:
            actions.append({'action': 'create', 'kind': 'monitor', 'name': wanted['name'], 'body': wanted})
            continue
        if existing['type'] != wanted['type']:
            raise SyncError(f'Monitor "{wanted["name"]}" exists as {existing["type"]}, not {wanted["type"]}. '
                            'A monitor\'s type can\'t change: rename it in the manifest and prune the old one.')

        changes = {field: value for field, value in wanted.items()
                   if field in MONITOR_FIELDS and existing.get(field) != value}
        # Minutes sent alone clear the seconds override, so keep the manifest's.
        if 'check_interval_minutes' in changes and 'check_interval_seconds' in wanted:
            changes['check_interval_seconds'] = wanted['check_interval_seconds']
        if 'password' in wanted and wanted['password'] and not existing.get('has_password'):
            changes['password'] = wanted['password']
        current = sorted(contact['name'] for contact in existing.get('notification_contacts', []))
        if sorted(wanted['notify']) != current:
            changes['notify'] = wanted['notify']
        if changes:
            before = {field: existing.get(field) for field in changes if field != 'password'}
            if 'notify' in changes:
                before['notify'] = current
            actions.append({'action': 'update', 'kind': 'monitor', 'name': wanted['name'], 'id': existing['id'],
                            'body': changes, 'before': before})

    for name, existing in sorted(remote.items()):
        actions.append({'action': 'delete' if prune else 'orphan', 'kind': 'monitor', 'name': name, 'id': existing['id']})

    return actions


def describe(action: dict) -> str:
    kind, name = action['kind'], action['name']
    if action['action'] == 'create':
        body = action['body']
        details = [f'{body["type"]} {body["url"]}' if body.get('url') else body['type']]
        if kind == 'monitor':
            seconds = body.get('check_interval_seconds')
            details.append(f'every {seconds} s' if seconds else f'every {body["check_interval_minutes"]} min')
            if body.get('is_active') is False:
                details.append('paused')
        return f'+ create {kind} "{name}" ({", ".join(details)})'
    if action['action'] == 'update':
        changes = ', '.join(
            f'{field} {json.dumps(action["before"].get(field))} -> {json.dumps(value)}' if field != 'password' else 'password'
            for field, value in action['body'].items()
            if not (kind == 'contact' and field == 'config')
        )
        if kind == 'contact' and 'config' in action['body']:
            changes = ', '.join(filter(None, [changes, 'config']))
        return f'~ update {kind} "{name}": {changes}'
    if action['action'] == 'delete':
        return f'- delete {kind} "{name}"'
    return f'! {kind} "{name}" is not in the manifest (apply --prune deletes it)'


def check_intervals(actions: list[dict], team: dict) -> None:
    """Refuse intervals shorter than the team's plan allows, before anything is written."""
    problems = []
    for action in actions:
        if action['kind'] != 'monitor' or action['action'] not in ('create', 'update'):
            continue
        body = action['body']
        minutes, seconds = body.get('check_interval_minutes'), body.get('check_interval_seconds')
        if minutes is not None and minutes < team['min_interval_minutes']:
            problems.append(f'"{action["name"]}" checks every {minutes} min, but the {team["plan"]} plan checks at most '
                            f'every {team["min_interval_minutes"]} minutes.')
        if seconds is not None and seconds < team['min_interval_seconds']:
            problems.append(f'"{action["name"]}" checks every {seconds} s, but the {team["plan"]} plan checks at most '
                            f'every {team["min_interval_seconds"]} seconds.')
    if problems:
        raise SyncError('\n'.join(problems) + '\nRaise the intervals in the manifest, or ask an Owner to upgrade the plan.')


# ---------------------------------------------------------------- applying

def apply_actions(api: Api, actions: list[dict]) -> None:
    contact_ids = {contact['name']: contact['id'] for contact in api.contacts()}

    for action in [a for a in actions if a['kind'] == 'contact']:
        if action['action'] == 'create':
            created = api.request('POST', '/notification-contacts', action['body'])['data']
            contact_ids[created['name']] = created['id']
        else:
            api.request('PATCH', f'/notification-contacts/{action["id"]}', action['body'])
        print(describe(action))

    for action in [a for a in actions if a['kind'] == 'monitor']:
        if action['action'] == 'orphan':
            print(describe(action))
            continue
        if action['action'] == 'delete':
            api.request('DELETE', f'/monitors/{action["id"]}')
            print(describe(action))
            continue

        body = {key: value for key, value in action['body'].items() if key != 'notify'}
        if 'notify' in action['body']:
            body['notification_contact_ids'] = [contact_ids[name] for name in action['body']['notify']]
        if action['action'] == 'create':
            api.request('POST', '/monitors', body)
        else:
            body.pop('type', None)
            api.request('PATCH', f'/monitors/{action["id"]}', body)
        print(describe(action))


def ping_urls(project: str, monitors: list[dict]) -> dict[str, str]:
    prefix = f'{project}: '
    return {
        env_name(monitor['name'][len(prefix):]): monitor['heartbeat_url']
        for monitor in monitors
        if monitor['name'].startswith(prefix) and monitor.get('heartbeat_url')
    }


def write_env_file(path: str, values: dict[str, str]) -> None:
    lines = []
    if os.path.exists(path):
        with open(path, encoding='utf-8') as handle:
            lines = handle.read().splitlines()

    remaining = dict(values)
    for index, line in enumerate(lines):
        key = line.split('=', 1)[0].strip()
        if key in remaining:
            lines[index] = f'{key}={remaining.pop(key)}'
    lines.extend(f'{key}={value}' for key, value in remaining.items())

    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines) + '\n')

    folder, name = os.path.split(os.path.abspath(path))
    try:
        ignored = subprocess.run(['git', '-C', folder, 'check-ignore', '-q', name], capture_output=True).returncode == 0
    except OSError:
        print(f'warning: git is not available to check that {path} is ignored. Ping URLs are secrets; '
              'keep them out of the repository.', file=sys.stderr)
        return
    if not ignored:
        print(f'warning: {path} is not ignored by git. Ping URLs are secrets; keep them out of the repository.',
              file=sys.stderr)


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync alls-well.json with All's Well.")
    parser.add_argument('command', choices=('validate', 'plan', 'apply'))
    parser.add_argument('--manifest', default='alls-well.json', help='path to the manifest (default: alls-well.json)')
    parser.add_argument('--prune', action='store_true', help="delete this project's monitors that the manifest no longer lists")
    parser.add_argument('--check', action='store_true', help='with plan: exit 2 if anything would change')
    parser.add_argument('--env-file', help='with apply: write ALLS_WELL_PING_* lines for heartbeat monitors into this file')
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
        missing: set = set()
        manifest = interpolate(manifest, missing)

        if args.command == 'validate':
            print(f'{args.manifest} is valid: {len(manifest["monitors"])} monitors, {len(manifest.get("contacts", []))} contacts.')
            if missing:
                print(f'Set these before plan or apply: {", ".join(sorted(missing))}')
            defined = {contact['name'] for contact in manifest.get('contacts', [])}
            named = {name for monitor in manifest['monitors'] for name in monitor.get('notify', manifest.get('notify', []))}
            if named - defined:
                print(f'Not defined here, so these must already be contacts in the team (plan checks): '
                      f'{", ".join(sorted(named - defined))}')
            return 0

        if missing:
            raise SyncError(f'Set these environment variables first: {", ".join(sorted(missing))}')
        token = os.environ.get('ALLS_WELL_TOKEN')
        if not token:
            raise SyncError('Set ALLS_WELL_TOKEN to a team API token (Settings, API tokens; Owner or Admin).')

        api = Api(os.environ.get('ALLS_WELL_URL') or manifest.get('url') or DEFAULT_URL, token)
        actions = plan_changes(manifest, api.monitors(), api.contacts(), args.prune)
        changes = [a for a in actions if a['action'] != 'orphan']

        creates = sum(1 for a in changes if a['kind'] == 'monitor' and a['action'] == 'create')
        deletes = sum(1 for a in changes if a['kind'] == 'monitor' and a['action'] == 'delete')
        team = api.team()
        if creates and team['max_monitors'] is not None and team['monitors_used'] - deletes + creates > team['max_monitors']:
            raise SyncError(f'This needs {creates} new monitors but the {team["plan"]} plan has room for '
                            f'{team["max_monitors"] - team["monitors_used"] + deletes}. Trim the manifest or upgrade the plan.')

        check_intervals(changes, team)

        if args.command == 'plan':
            for action in actions:
                print(describe(action))
            if not changes:
                print('No changes.')
            return 2 if args.check and changes else 0

        apply_actions(api, actions)
        if not changes:
            print('No changes.')

        urls = ping_urls(manifest['project'].strip(), api.monitors())
        if urls:
            if args.env_file:
                write_env_file(args.env_file, urls)
                print(f'Wrote {len(urls)} heartbeat ping URL(s) to {args.env_file}.')
            else:
                print(f'Heartbeat ping URLs are ready for {", ".join(urls)}. They are secrets, so they are not printed: '
                      'run apply again with --env-file FILE (a file git ignores) to write them.')
        return 0
    except SyncError as error:
        print(f'error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
