# The Cloudflare API with curl

Each step of `SKILL.md` as a request to `https://api.cloudflare.com/client/v4`. Every response is wrapped: `{"success": true, "errors": [], "result": …}`. When `success` is `false`, `errors[].message` says why.

The token is the person's, in `CLOUDFLARE_API_TOKEN`, with the permissions `SKILL.md` lists. Never print it or write it to a file.

```bash
CF=https://api.cloudflare.com/client/v4
auth=(-H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json")
```

## The zone

```bash
curl -sS "${auth[@]}" "$CF/zones?name=example.com" \
  | jq '.result[] | {id, name, plan: .plan.legacy_id, account: .account.id}'
ZONE_ID=…        # id
ACCOUNT_ID=…     # account
```

Bot Fight Mode is on when `fight_mode` is `true`:

```bash
curl -sS "${auth[@]}" "$CF/zones/$ZONE_ID/bot_management" | jq '.result'
```

## Security Events (step 2)

`jq` builds the body, so the query needs no shell escaping:

```bash
since=$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-24H +%Y-%m-%dT%H:%M:%SZ)

jq -n --arg zone "$ZONE_ID" --arg since "$since" '{
  query: "query ($zoneTag: string, $since: Time) { viewer { zones(filter: { zoneTag: $zoneTag }) { firewallEventsAdaptiveGroups(filter: { datetime_geq: $since, userAgent_like: \"AllsWell/%\" }, limit: 25, orderBy: [count_DESC]) { count dimensions { clientIP clientAsn clientCountryName source action ruleId } } } } }",
  variables: {zoneTag: $zone, since: $since}
}' | curl -sS "${auth[@]}" "$CF/graphql" --data @- \
  | jq '{errors, events: .data.viewer.zones[0].firewallEventsAdaptiveGroups}'
```

GraphQL answers `200` even when the query fails, so read `errors` first. A token without Analytics Read gets an authorization error there.

## An IP list (step 3)

Only when the addresses go in a list rather than inline. List the account's lists first, to reuse `agile_pixel_services` or to see whether there is room:

```bash
curl -sS "${auth[@]}" "$CF/accounts/$ACCOUNT_ID/rules/lists" | jq '.result[] | {id, name, kind, num_items}'
```

Create it, if it isn't there:

```bash
curl -sS "${auth[@]}" -X POST "$CF/accounts/$ACCOUNT_ID/rules/lists" \
  --data '{"name": "agile_pixel_services", "kind": "ip", "description": "Agile Pixel services"}' \
  | jq '{id: .result.id, errors}'
LIST_ID=…
```

Add the confirmed addresses. This adds to the list and leaves its other items alone:

```bash
jq -n '[{ip: "192.0.2.10", comment: "All'"'"'s Well checker"}, {ip: "2001:db8::10", comment: "All'"'"'s Well checker"}]' \
  | curl -sS "${auth[@]}" -X POST "$CF/accounts/$ACCOUNT_ID/rules/lists/$LIST_ID/items" --data @- \
  | jq '{operation_id: .result.operation_id, errors}'
```

Wait for the operation: its `status` goes from `pending` or `running` to `completed` (or `failed`, with an `error`):

```bash
curl -sS "${auth[@]}" "$CF/accounts/$ACCOUNT_ID/rules/lists/bulk_operations/$OPERATION_ID" | jq '.result'
```

To remove an address All's Well no longer uses, find its item ID and delete that item only:

```bash
curl -sS "${auth[@]}" "$CF/accounts/$ACCOUNT_ID/rules/lists/$LIST_ID/items" | jq '.result[] | {id, ip, comment}'
curl -sS "${auth[@]}" -X DELETE "$CF/accounts/$ACCOUNT_ID/rules/lists/$LIST_ID/items" \
  --data '{"items": [{"id": "<item id>"}]}' | jq '{operation_id: .result.operation_id, errors}'
```

## The skip rule (steps 4 and 5)

Put the rule from `SKILL.md`, with the confirmed addresses, in a shell variable:

```bash
RULE=$(cat <<'EOF'
{
  "ref": "agile_pixel_services",
  "description": "Agile Pixel services: let All's Well uptime checks through",
  "expression": "(ip.src in {192.0.2.10 2001:db8::10} and http.user_agent contains \"AllsWell/\")",
  "action": "skip",
  "action_parameters": {
    "ruleset": "current",
    "phases": ["http_ratelimit", "http_request_firewall_managed", "http_request_sbfm"],
    "products": ["zoneLockdown", "uaBlock", "bic", "hot", "securityLevel"]
  },
  "logging": {"enabled": true},
  "position": {"before": ""}
}
EOF
)
```

Read the zone's custom rules:

```bash
curl -sS "${auth[@]}" "$CF/zones/$ZONE_ID/rulesets/phases/http_request_firewall_custom/entrypoint" \
  | jq '{success, errors, ruleset_id: .result.id, rules: [.result.rules[]? | {id, ref, description, action, enabled}]}'
RULESET_ID=…   # ruleset_id
RULE_ID=…      # the id of the rule whose ref is agile_pixel_services, if there is one
```

Then validate the matching write with `?dry_run=true`, show the person, and send it again without `dry_run`. A successful validation returns `"success": true` with `"result": null`.

The rule exists: update it.

```bash
curl -sS "${auth[@]}" -X PATCH "$CF/zones/$ZONE_ID/rulesets/$RULESET_ID/rules/$RULE_ID?dry_run=true" \
  --data "$RULE" | jq '{success, errors}'
```

The ruleset exists, the rule doesn't: add it.

```bash
curl -sS "${auth[@]}" -X POST "$CF/zones/$ZONE_ID/rulesets/$RULESET_ID/rules?dry_run=true" \
  --data "$RULE" | jq '{success, errors}'
```

The read returned `404`: create the ruleset with the rule in it.

```bash
jq -n --argjson rule "$RULE" \
  '{name: "default", kind: "zone", phase: "http_request_firewall_custom", rules: [$rule | del(.position)]}' \
  | curl -sS "${auth[@]}" -X POST "$CF/zones/$ZONE_ID/rulesets?dry_run=true" --data @- \
  | jq '{success, errors}'
```

Never send `PUT …/rulesets/phases/http_request_firewall_custom/entrypoint`: it replaces every custom rule on the zone.

## An IP Access rule for Bot Fight Mode (step 4)

One per confirmed address, on the zone. Check for an existing one first, so you don't add it twice:

```bash
curl -sS "${auth[@]}" "$CF/zones/$ZONE_ID/firewall/access_rules/rules?notes=Agile%20Pixel%20services" \
  | jq '.result[] | {id, mode, configuration, notes}'

jq -n --arg ip 192.0.2.10 \
  '{mode: "whitelist", configuration: {target: "ip", value: $ip}, notes: "Agile Pixel services: All'"'"'s Well checker"}' \
  | curl -sS "${auth[@]}" -X POST "$CF/zones/$ZONE_ID/firewall/access_rules/rules" --data @- \
  | jq '{id: .result.id, errors}'
```

Use `target: "ip6"` for an IPv6 address. These requests have no `dry_run`: show the person the addresses before sending them.
