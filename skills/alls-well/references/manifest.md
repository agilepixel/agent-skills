# alls-well.json

The manifest names a project and describes its monitors and alert contacts. `scripts/alls_well_sync.py` makes All's Well match it. Editors that read `$schema` validate it against `manifest.schema.json`.

## Top level

| Field | Required | Content |
|---|---|---|
| `$schema` | No | `https://alls-well.io/docs/api/skill/references/manifest.schema.json` |
| `project` | Yes | The name of the project in All's Well, such as `"Northwind shop"`. The value does two jobs: it links this codebase to its All's Well project, which shows on the website and groups the monitors, and it is the prefix in every monitor's name, `<project>: <name>`. `apply` finds the project by key, by name or by a name it had before a rename, and creates it when the team has none. If someone renames the project on the website, keep the value as it is: All's Well remembers every name a project has had, so it still finds the project. Changing it makes the sync treat every monitor as new |
| `url` | No | The All's Well instance, when it isn't `https://alls-well.io`. `ALLS_WELL_URL` overrides it |
| `notify` | No | Contact names alerted by monitors that don't set their own `notify`. A monitor with neither is refused. `[]` attaches no contacts on purpose, so the monitor alerts every confirmed contact on the team |
| `contacts` | No | Contacts to create or update (below) |
| `monitors` | No | The monitors to sync (below). Leave it out when monitors are recorded through MCP: a manifest of just `{"project": "Northwind shop"}` is valid, and `apply` only makes sure the project exists |

## Contacts

Matched by `name` across the whole team, so a contact the team already has can be named in `notify` without being listed here. Listed contacts are created when missing and updated when different. They are never deleted.

An `email` contact created here, or whose address changes, gets no alerts until the person at that address confirms through the link All's Well emails them, unless the team already alerts that address. Meanwhile a monitor whose `notify` names only unconfirmed contacts alerts the team owner instead. An address that declined on the team stays declined; only a person on the web can add it again.

| Field | Required | Content |
|---|---|---|
| `name` | Yes | Unique in the team |
| `type` | Yes | `email`, `slack`, `discord`, `webhook` or `telegram`. Can't change later |
| `config` | Yes | `email` → `{"email": …}`; `slack`, `discord` → `{"webhook_url": …}`; `webhook` → `{"url": …}`; `telegram` → `{"bot_token": …, "chat_id": …}`. Put secrets in `${VAR}` |
| `notify_on_down` | No | Default `true` |
| `notify_on_recovery` | No | Default `true` |

## Monitors

Matched by `<project>: <name>`, and kept in the project: `apply` puts each monitor it creates in the project, and moves a monitor with the prefix into this project, including out of another project if it was filed elsewhere. That linking, like creating the project, isn't drift: `plan --check` prints it as a `note:` line and exits 2 only when a monitor or contact itself would change. The sync never clears a monitor's project. `--prune` still matches only the name prefix. Against an All's Well server that predates projects, or when the team can't have the project (a `402` at the plan's project limit, or a `403` for a token that may not create projects), monitors are synced without one. Fields left out keep whatever All's Well has, except `check_interval_minutes`, which defaults to 5.

A monitor `apply` creates, or whose check it changes (`url`, `expected_keyword`, `port`, `http_method`, `expected_status_codes`, `request_headers`, `username` or `password`), proves itself first: until it has 3 good checks in a row, or a heartbeat its first on-time ping, its alerts go only to the token's owner and its `notify` contacts are held. See step 4 of the skill.

| Field | Types | Content |
|---|---|---|
| `name` | all | Unique in the manifest. Renaming creates a new monitor; the old one is reported as orphaned until `apply --prune` |
| `type` | all | `http`, `keyword`, `ssl`, `tcp`, `icmp` or `heartbeat`. Can't change later |
| `url` | all but `heartbeat` | A full URL. `tcp` and `icmp` use only its host |
| `check_interval_minutes` | all | 1, 5, 15, 30 or 60, at least the plan's minimum (Free: 5) |
| `check_interval_seconds` | all | An exact interval that overrides the minutes, at least the plan's `min_interval_seconds`. `null` removes the override. Use it when the interval isn't one of the minute values, which a heartbeat's usually isn't (a daily job needs 90000) |
| `is_active` | all | `false` pauses the monitor. Start heartbeats paused until their ping is deployed |
| `notify` | all | Contact names; replaces the top-level `notify` for this monitor. `[]` attaches none, so the monitor alerts every confirmed contact on the team. While the monitor proves itself these are held, and attached once it is proven |
| `expected_keyword` | `keyword` | Text the page must contain |
| `http_method` | `http`, `keyword` | Default `GET` |
| `expected_status_codes` | `http`, `keyword` | Default `[200]` |
| `request_timeout_seconds` | `http`, `keyword` | 1 to 60, default 30 |
| `request_headers` | `http`, `keyword` | `{"Name": "value"}`; use `${VAR}` for credentials |
| `username`, `password` | `http`, `keyword` | Basic auth. Use `${VAR}`. The password is sent only when All's Well has none stored |
| `port` | `tcp` | 1 to 65535 |
| `ssl_expiry_warning_days` | `ssl` | 1 to 90, default 14 |

## Examples

A static marketing site:

```json
{
  "project": "Northwind marketing",
  "notify": ["Ops email"],
  "monitors": [
    {"name": "Home page", "type": "keyword", "url": "https://www.example.com", "expected_keyword": "Northwind Coffee", "check_interval_minutes": 5},
    {"name": "Certificate", "type": "ssl", "url": "https://www.example.com", "check_interval_minutes": 60}
  ]
}
```

An API behind basic auth, with a database port and a queue worker heartbeat:

```json
{
  "project": "Northwind API",
  "notify": ["Ops email", "On-call webhook"],
  "contacts": [
    {"name": "On-call webhook", "type": "webhook", "config": {"url": "${ONCALL_WEBHOOK_URL}"}}
  ],
  "monitors": [
    {"name": "Health", "type": "http", "url": "https://api.example.com/health", "check_interval_minutes": 5,
     "username": "monitor", "password": "${API_HEALTH_PASSWORD}", "expected_status_codes": [200]},
    {"name": "Postgres", "type": "tcp", "url": "https://db.example.com", "port": 5432, "check_interval_minutes": 5},
    {"name": "Queue worker", "type": "heartbeat", "check_interval_seconds": 1200, "is_active": false}
  ]
}
```
