# The cf CLI

Each step of `SKILL.md` with `cf`, Cloudflare's CLI for its whole API (in beta). Install it with `npm install -g cf`.

## Signing in

- On the person's machine: they run `cf auth login` themselves, because it opens a browser. `cf auth whoami` shows who is signed in, and `cf auth scopes` shows what the login is allowed to do.
- In CI, or anywhere nobody can sign in: `CLOUDFLARE_API_TOKEN`, with the permissions `SKILL.md` lists. It takes priority over a login.
- Set `CLOUDFLARE_ACCOUNT_ID` for the list commands.

## How cf behaves

| Behaviour | What it means here |
|---|---|
| Results are the API's `result`, as JSON on stdout; messages go to stderr | Pipe to `jq` |
| `rulesets` and `firewall access-rules` run against the account unless you pass `--zone`, and ignore `CLOUDFLARE_ZONE_ID` | Always pass `--zone "$ZONE_ID"` to them |
| `--body` takes the JSON request body | Use it for rules, lists and IP Access rules |
| `--dry-run` prints the request without sending it | Use it to check what will be sent; it validates nothing |
| `--validate-only` sends the request with `dry_run=true` | Cloudflare validates the rule and changes nothing |
| A failed command exits non-zero, with the error on stderr | Check the exit status |
| Command names come from the API and can change during the beta | If one isn't found, run `cf cli search "<the task>"` and `cf schema <command>`. Describe only the task: no domains, IDs or addresses |

There is no `cf` command for Security Events (step 2). Send the GraphQL request in `api.md` with a token that has Analytics Read, use the MCP server's `execute` (`mcp.md`), or ask the person to read **Security, Analytics, Events** in the dashboard.

## The zone

```bash
cf zones list --name example.com | jq '.[] | {id, name, plan: .plan.legacy_id, account: .account.id}'
cf bot-management get --zone "$ZONE_ID" | jq '{fight_mode}'
```

## An IP list (step 3)

```bash
cf rules lists list | jq '.[] | {id, name, kind, num_items}'
cf rules lists create --body '{"name": "agile_pixel_services", "kind": "ip", "description": "Agile Pixel services"}' | jq '{id}'
cf rules lists items create "$LIST_ID" \
  --body "$(jq -n '[{ip: "192.0.2.10", comment: "All'"'"'s Well checker"}]')" | jq -r '.operation_id'
cf rules lists bulk-operations get "$OPERATION_ID" | jq '{status, error}'
cf rules lists items list --list-id "$LIST_ID" | jq '.[] | {id, ip, comment}'
```

Never use `cf rules lists items update`: it replaces all of the list's items. Remove one with `cf rules lists items delete "$LIST_ID" --body '{"items": [{"id": "<item id>"}]}'`.

## The skip rule (steps 4 and 5)

`$RULE` is the rule from `SKILL.md`, set as in `api.md`.

Read the zone's custom rules. A `404` error means it has none yet:

```bash
cf rulesets entrypoint get http_request_firewall_custom --zone "$ZONE_ID" \
  | jq '{id, rules: [.rules[]? | {id, ref, description, action, enabled}]}'
```

Validate the matching write with `--validate-only`, show the person, then run it again without the flag:

```bash
# The rule exists (its ref is agile_pixel_services): update it
cf rulesets rules update "$RULE_ID" --ruleset-id "$RULESET_ID" --zone "$ZONE_ID" --body "$RULE" --validate-only

# The ruleset exists, the rule doesn't: add it
cf rulesets rules create "$RULESET_ID" --zone "$ZONE_ID" --body "$RULE" --validate-only

# No custom rules yet: create the ruleset with the rule in it
cf rulesets create --zone "$ZONE_ID" --validate-only --body "$(jq -n --argjson rule "$RULE" \
  '{name: "default", kind: "zone", phase: "http_request_firewall_custom", rules: [$rule | del(.position)]}')"
```

Never run `cf rulesets entrypoint update`: it replaces every custom rule on the zone.

## An IP Access rule for Bot Fight Mode (step 4)

One per confirmed address. List the ones already there first, so you don't add one twice:

```bash
cf firewall access-rules list --zone "$ZONE_ID" --notes "Agile Pixel services" | jq '.[] | {id, mode, configuration}'
cf firewall access-rules create --zone "$ZONE_ID" --body "$(jq -n --arg ip 192.0.2.10 \
  '{mode: "whitelist", configuration: {target: "ip", value: $ip}, notes: "Agile Pixel services: All'"'"'s Well checker"}')"
```

Use `target: "ip6"` for an IPv6 address. There is no `--validate-only` here: show the person the addresses first.
