---
name: alls-well
description: Use when adding uptime monitoring, heartbeat or cron-job monitoring, SSL certificate checks, downtime alerts or a status badge to a project with All's Well, or when connecting a project's servers, WordPress sites or deploy pipeline to All's Well.
---

# All's Well

You integrate a project with All's Well so that everything that can fail is watched, the right people are alerted, and the setup lives in the project's repository as `alls-well.json`, where it can be reviewed and applied again.

## When This Skill Applies

Trigger this skill when asked to:
- Monitor a site, API, certificate, port or host
- Alert someone when a scheduled job (cron, Laravel scheduler, systemd timer, CI schedule) stops running
- Connect a server or a WordPress site to All's Well
- Add a status badge, or change who gets alerts

For a one-off question answered in conversation, an AI assistant can use the All's Well MCP server instead (`${ALLS_WELL_URL:-https://alls-well.io}/docs/api/mcp.md`). For anything that belongs to a project, use the manifest below.

## Before You Start

| Need | How |
|---|---|
| A team API token | An Owner or Admin creates one in **Settings, API tokens**. Ask the person for it. Keep it in `ALLS_WELL_TOKEN`, quoted because tokens contain `\|`: `export ALLS_WELL_TOKEN='3\|…'`. Never write it into a file in the repository |
| The base URL | `ALLS_WELL_URL`, default `https://alls-well.io`. For any other instance, also set `"url"` in the manifest so teammates and CI reach the same one |
| Room on the plan | `curl -s "${ALLS_WELL_URL:-https://alls-well.io}/api/v1/team" -H "Authorization: Bearer $ALLS_WELL_TOKEN"`: check `can_add_monitor`, `max_monitors`, `min_interval_minutes`, and `min_interval_seconds` for heartbeats and other exact intervals |

The full reference is `${ALLS_WELL_URL:-https://alls-well.io}/docs/api.md` (Markdown) and `/docs/api/openapi.yaml` beside it. Read it only for something this skill doesn't cover.

## 1. Survey the Project

Read the code for what can fail. Ask the person for anything you can't find; never guess a production URL or who should be alerted.

- Before choosing a keyword, fetch the page and confirm it contains the text (`curl -fsS <url> | grep -c '<text>'`). If you can't fetch it, use an `http` monitor and ask the person for a keyword.
- A site or service with its own repository belongs in that repository's manifest. Ask before monitoring it from this one.

| Look in | For | Becomes |
|---|---|---|
| `APP_URL`, `.env.example`, deploy config, README | Production hosts | A `keyword` monitor on the page customers depend on, with text that only renders when the app works (a product name, "Add to basket"); an `ssl` monitor per HTTPS host |
| Health routes (Laravel's `health: '/up'`) | A health endpoint | An `http` monitor, when it checks more than the page above does |
| `routes/console.php`, `app/Console/Kernel.php`, crontabs, systemd timers, `on: schedule` workflows, WP-Cron | Scheduled jobs | A `heartbeat` monitor per job whose silence would hurt |
| Hosting docs, deploy scripts, Ansible, Terraform | Servers | The server agent: a person installs it (step 6) |
| WordPress sites | Sites | The WordPress plugin: a person connects it (step 6) |
| Publicly reachable databases, mail or game servers | Ports | A `tcp` monitor |

## 2. Write `alls-well.json`

Before writing monitors, ask whether the team wants them recorded through MCP or in the manifest:

- **In the manifest** is the flow below: the file lists every monitor, and `apply` makes All's Well match it.
- **Through MCP:** the file holds just the project, `{"project": "Northwind shop"}`, and `apply` only makes sure the project exists. An agent with the All's Well MCP server then uses `create-project` (or `get-project` when it exists) and `move-to-project` to organise the items it records, and creates monitors with the `project` argument. Skip steps 3 to 5 for monitors recorded this way.

Commit it at the project root:

```json
{
  "$schema": "https://alls-well.io/docs/api/skill/references/manifest.schema.json",
  "project": "Northwind shop",
  "notify": ["Ops email"],
  "contacts": [
    {"name": "Ops email", "type": "email", "config": {"email": "ops@example.com"}},
    {"name": "Ops Slack", "type": "slack", "config": {"webhook_url": "${SLACK_WEBHOOK_URL}"}, "notify_on_recovery": false}
  ],
  "monitors": [
    {"name": "Storefront", "type": "keyword", "url": "https://shop.example.com", "expected_keyword": "Add to basket", "check_interval_minutes": 5, "notify": ["Ops email", "Ops Slack"]},
    {"name": "Certificate", "type": "ssl", "url": "https://shop.example.com", "check_interval_minutes": 60, "ssl_expiry_warning_days": 21},
    {"name": "Nightly backup", "type": "heartbeat", "check_interval_seconds": 90000, "is_active": false},
    {"name": "Fulfilment sync", "type": "heartbeat", "check_interval_seconds": 5400, "is_active": false}
  ]
}
```

| Rule | Why |
|---|---|
| `project` names the All's Well project and never changes | It shows on the website, where the project groups this codebase's monitors. Every monitor is named `<project>: <name>`; that prefix is how the sync knows which are this project's. `apply` creates the project when the team has none, and puts the monitors in it |
| Secrets are `${ENV_VAR}` | The manifest is committed; webhook URLs and bot tokens are credentials |
| `notify` at the top is the default for every monitor | A monitor with no contacts alerts every confirmed contact on the team, which is rarely what a project means, so `validate` refuses one unless it says `"notify": []` |
| Contacts are ones the person names | Ask who should be alerted rather than inventing a contact. `validate` lists the names that aren't defined in the manifest; `plan` refuses any that isn't a contact in the team |
| A new email address must confirm | All's Well emails it a link, and it gets no alerts until the person there confirms. Tell the person who to expect it (step 4) |
| Intervals are at least the plan's minimum | Free checks every 5 minutes at most, so `check_interval_minutes: 1` needs a paid plan; check `min_interval_minutes` first |
| A new heartbeat starts with `"is_active": false` | It goes down at once if no ping arrives; switch it on once the ping is deployed |
| A heartbeat's interval is the job's period plus its run time plus a margin | There is no grace period. Daily: `check_interval_seconds: 90000`; hourly: `5400` |
| `url` is a full URL, even for `tcp` and `icmp` | A bare hostname is rejected; only the host is used |

Every field, and more examples, are in `references/manifest.md`.

## 3. Sync It

The sync script is `scripts/alls_well_sync.py` in this skill's directory. It needs Python 3.9 or later and nothing else.

```bash
python3 <skill-dir>/scripts/alls_well_sync.py validate                  # no network
python3 <skill-dir>/scripts/alls_well_sync.py plan                      # what would change
python3 <skill-dir>/scripts/alls_well_sync.py apply --env-file .alls-well.env   # do it; write ping URLs
```

- Show the person the `plan` before `apply` whenever it updates or deletes anything.
- `apply` is idempotent: run it again after every manifest change. It never deletes unless you pass `--prune`, and then only monitors named with this project's prefix. Use `--prune` only when the person asks for monitors to go.
- `apply` also makes sure the project exists. When the team can't have it, because of a `402` (the plan's project limit) or a `403` (a token that may not create projects), `apply` says so in one line and syncs the monitors without a project, as it does against an All's Well server older than projects. A `403` on a monitor still stops it. `plan` says "would create project" without creating it.
- `plan` and `apply` refuse intervals shorter than the plan allows, before writing anything.
- `--env-file` writes `ALLS_WELL_PING_<NAME>=<url>` for each heartbeat; without it, the URLs aren't printed. Add `.alls-well.env` to `.gitignore` first; the script warns if it isn't ignored. Don't write them into the local `.env`: a local scheduler run would then ping production. The person moves them into production's environment and deletes the file.
- Other developers and CI get the script from `${ALLS_WELL_URL:-https://alls-well.io}/docs/api/skill/scripts/alls_well_sync.py`. Say so in the project's README next to how to run it. Don't point the README at this skill: the repository may be handed over to the client.
- For drift detection in CI: `plan --check` exits 2 when a monitor or contact no longer matches the manifest. Linking to the project, by creating it or moving this project's monitors into it, isn't drift: `plan --check` prints it as a `note:` line and `apply` does it.

## 4. Check the First Results

Monitors that `apply` creates, and monitors whose check it changes (`url`, `expected_keyword`, `port`, `http_method`, `expected_status_codes`, `request_headers`, `username` or `password`), prove themselves before they alert anyone else. Changing only the name, interval, timeout or `is_active` doesn't count.

- **Until it is proven,** a monitor's alerts go only to the owner of the token that made the change, including the recovery of an outage that began before the change. It is proven by 3 good checks in a row (`up` or `degraded`), or a heartbeat's first on-time ping; any other result starts the count again.
- **The contacts in its `notify` are held meanwhile.** The API lists them in `notification_contacts` with `held: true`, and `proving.held_requested_at` says when they were asked for. They are attached by themselves once it is proven, and the token's owner stops getting its alerts. `plan --check` counts held contacts as in step, so CI sees no drift.
- **Held contacts lapse after 7 days switched on** without proving, and the token's owner gets an email. Paused time doesn't count, so a heartbeat created paused starts its clock when it is switched on.
- **A new email contact, or one whose address changes, confirms first.** It gets nothing until the person at that address confirms through the link All's Well emails them. If they choose "This wasn't me", the address is declined on that team for good: `apply` can't add it again, only a person on the web can.
- **A proven monitor whose contacts are all `pending` or `declined` alerts only the team owner** until one of them confirms, never the team's other contacts.

A few minutes after `apply`, read this project's monitors (named `<project>: …`), the first checks of each new or changed one, and the contacts:

```bash
curl -s "${ALLS_WELL_URL:-https://alls-well.io}/api/v1/monitors?per_page=100" -H "Authorization: Bearer $ALLS_WELL_TOKEN"   # proving, notification_contacts[].held
curl -s "${ALLS_WELL_URL:-https://alls-well.io}/api/v1/monitors/<id>/checks" -H "Authorization: Bearer $ALLS_WELL_TOKEN"     # status, error_message
curl -s "${ALLS_WELL_URL:-https://alls-well.io}/api/v1/notification-contacts" -H "Authorization: Bearer $ALLS_WELL_TOKEN"    # confirmation
```

Then tell the person:

- which monitors are still proving, and that until then their alerts go only to the token's owner
- which contacts are held, and that they join once each monitor is proven
- which addresses are `pending`, so those people expect the confirmation email, and any that `declined`
- any monitor whose first checks are `down` or `blocked`: fix the URL or keyword, or allow-list the checkers, before its held contacts lapse

## 5. Wire Each Heartbeat

Each job requests its ping URL after it succeeds. In Laravel:

```php
// config/services.php
'alls_well' => ['pings' => [
    'nightly_backup' => env('ALLS_WELL_PING_NIGHTLY_BACKUP'),
]],

// routes/console.php
Schedule::command('backup:run')->dailyAt('02:00')
    ->pingOnSuccessIf(filled($url = config('services.alls_well.pings.nightly_backup')), $url);
```

If the project has removed `config/services.php`, recreate it with only the `alls_well` key; Laravel merges it with its defaults. Add each variable to `.env.example` with an empty value. Cron, systemd, GitHub Actions, Node, WordPress, containers and queued jobs (which must ping from the job, not the scheduler) are in `references/heartbeats.md`.

Right after the change is deployed with the variables set in production, set `"is_active": true` on those heartbeats and run `apply` again. Until then each ping gets a `404`, which the scheduler logs. The first ping on time after that proves the heartbeat, and attaches its held contacts.

## 6. Hand Over What Only a Person Can Do

These have no API. End your work with a checklist the person can follow, with the exact steps from `references/manual-steps.md`:

| When the project has | The person |
|---|---|
| Servers (VPS, droplet, EC2) | Creates each in **Servers**, then runs its one-line install command on the server as root |
| WordPress sites | Installs the plugin from WordPress.org and clicks **Connect to All's Well** in its settings; for many sites, uses the team enrolment key |
| A need for a public status page or a README badge | Creates the status page and adds the monitors; a badge needs the monitor on a public page |
| Planned downtime | Adds a maintenance window |
| A WAF, Cloudflare or bot protection in front of the site | Allow-lists the All's Well checkers |
| Production secrets | Moves the `ALLS_WELL_PING_*` lines from `.alls-well.env` into production's environment, deletes the file, and sets the manifest's `${…}` variables wherever the sync runs |

## Alert Contacts

| Type | `config` |
|---|---|
| `email` | `email` |
| `slack`, `discord` | `webhook_url` |
| `webhook` | `url` (receives a JSON POST per alert) |
| `telegram` | `bot_token`, `chat_id` |

An email contact created or changed through the API stays `confirmation: pending`, and gets no alerts, until the person at that address confirms. Slack, Discord, Telegram and webhook contacts apply at once.

## Forbidden Patterns

| Don't | Do |
|---|---|
| Commit the API token, a ping URL or a webhook URL | Environment variables, `${VAR}` in the manifest, `.env` ignored by git |
| Paste a ping URL into chat, a PR description or a CI log | Refer to the variable name; link previews request the URL, which counts as a ping |
| Write production ping URLs into the local `.env` | `--env-file .alls-well.env`, ignored by git, moved to production by the person |
| Pick a keyword you haven't seen on the page | Fetch the page and check, or use `http` and ask |
| Create monitors one by one with `curl` or the MCP tools, when the team chose the manifest | Write the manifest and run the sync, so the setup is reviewable and repeatable |
| Name a monitor without the project's prefix | Let the sync name it from `project` |
| Create a heartbeat active before its ping is deployed | `"is_active": false`, then switch it on after the deploy |
| Make a heartbeat's interval equal to the job's period | Add the run time and a margin |
| Run `apply --prune` unasked | Show the `plan`; prune only on request |
| Tell the person their alerts are set up as soon as `apply` finishes | Check the first results (step 4): say which monitors are proving, which contacts are held and which addresses must confirm |

## Quick Reference

| Question | Answer |
|---|---|
| Where does the setup live? | `alls-well.json` in the project, applied with `scripts/alls_well_sync.py`. Its `project` is the All's Well project |
| Token? | `ALLS_WELL_TOKEN`, from Settings, API tokens (Owner or Admin) |
| Base URL? | `ALLS_WELL_URL`, default `https://alls-well.io` |
| Ping a heartbeat? | GET, HEAD or POST its `heartbeat_url` after each successful run |
| Daily job's interval? | `check_interval_seconds: 90000` |
| Slack contact? | `{"webhook_url": "..."}` |
| Plan full? | `402` with `monitor-limit-reached`: drop monitors or ask an Owner to upgrade |
| Server or WordPress? | A person does it: `references/manual-steps.md` |
| Why didn't a contact get the alert? | The monitor is still proving (alerts go only to the token's owner), or the contact is `pending` or `declined` |
