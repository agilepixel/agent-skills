---
name: cloudflare-allowlist
description: Use when an All's Well monitor says "Bot protection is blocking these checks", or a check fails with 401, 403 or 429 while the site works in a browser, and the site is behind Cloudflare; or when asked to allow-list All's Well or another Agile Pixel service in Cloudflare's WAF, Bot Fight Mode, Super Bot Fight Mode, Under Attack mode or security level. Finds the checker's addresses in Cloudflare's Security Events and adds one skip rule through the Cloudflare MCP server, the cf CLI or the API.
---

# Let Agile Pixel Services Through Cloudflare

You get Agile Pixel's services past Cloudflare's protection on a site without weakening it for anyone else: one custom rule that skips Cloudflare's checks only for requests that come from the service's IP addresses and carry its user agent. You find what is blocking the checks, confirm the addresses, show the person the rule, add it, and check that it worked.

## When This Applies

- All's Well shows **Bot protection is blocking these checks** on a monitor, or a check fails with 401, 403 or 429 while the page loads in a browser
- The person asks to allow-list or whitelist All's Well, or another Agile Pixel service, in Cloudflare
- You are setting up All's Well monitors (the `alls-well` skill) for a host served through Cloudflare and its zone has Bot Fight Mode, Super Bot Fight Mode, Under Attack mode or its own block or challenge rules: offer the rule before the first check fails

This skill covers Cloudflare only. For another CDN or firewall service (Sucuri, Imperva, Akamai, AWS WAF), the host's own protection or a WordPress security plugin, give the person the steps All's Well shows on the monitor's page.

## Agile Pixel Services

| Service | Reaches the site as | User agent | Addresses |
|---|---|---|---|
| All's Well uptime checks (`http` and `keyword` monitors) | HTTP requests to the monitored URL | `AllsWell/1.0 AgileMonitor/1.0 (+https://alls-well.io)` | Listed on the failing monitor's page in All's Well |

Only these need a rule. All's Well's heartbeats, server agent and WordPress plugin send from the site to All's Well, so they never pass through the site's Cloudflare, and `ssl`, `tcp` and `icmp` monitors never reach the WAF.

Anyone can send a user agent. The addresses are what make the rule safe; the user agent only narrows it further. Never allow on the user agent alone.

## Before You Start

| Need | How |
|---|---|
| A way in | The first of these that you have: the Cloudflare API MCP server (`references/mcp.md`); the `cf` CLI, signed in (`cf auth whoami`, `references/cf-cli.md`); the API with `curl` and `CLOUDFLARE_API_TOKEN` (`references/api.md`) |
| A token, for `cf` in CI or `curl` | The person creates one under **My Profile, API Tokens, Create Token, Create Custom Token**, limited to this zone and its account, with the permissions below. Keep it in `CLOUDFLARE_API_TOKEN`, quoted, and never in a file in the repository. Never use the Global API Key |
| The zone | Ask which site. The zone is the registered domain (`example.com`), not the host. Note its ID, account ID and plan (`plan.legacy_id`: `free`, `pro`, `business` or `enterprise`) |
| Access to the account | If the zone is in an account the person can't reach (often the client's), go to step 6 and hand it over |

| Permission | For |
|---|---|
| Zone, Zone, Read | Finding the zone and its plan |
| Zone, Analytics, Read | Security Events (step 2) |
| Zone, Zone WAF, Edit | The custom rule (steps 4 and 5) |
| Zone, Bot Management, Read | Checking whether Bot Fight Mode is on |
| Account, Account Filter Lists, Edit | Only with an IP list (step 3) |
| Zone, Firewall Services, Edit | Only for Bot Fight Mode (step 4) |

## 1. Confirm Cloudflare Is Answering

```bash
curl -sS -o /dev/null -D - -A 'AllsWell/1.0 AgileMonitor/1.0 (+https://alls-well.io)' https://shop.example.com/ \
  | grep -i -E '^(HTTP/|server:|cf-ray:|cf-mitigated:)'
```

| You see | It means |
|---|---|
| `server: cloudflare` and a `cf-ray` header | Cloudflare proxies the host: carry on |
| `cf-mitigated: challenge` as well | Cloudflare answered your request with a challenge page |
| A `200` from Cloudflare | Your address got through; the checker's can still be challenged, so carry on to step 2 |
| No `cf-ray` header | Cloudflare isn't proxying this host. The block is somewhere else: hand over the monitor page's steps |

## 2. Find What Blocks the Checks, and From Where

Query the zone's Security Events for the user agent over the last 24 hours. Each reference has the request for its interface; the query is the same:

```graphql
query ($zoneTag: string, $since: Time) {
  viewer {
    zones(filter: { zoneTag: $zoneTag }) {
      firewallEventsAdaptiveGroups(
        filter: { datetime_geq: $since, userAgent_like: "AllsWell/%" }
        limit: 25
        orderBy: [count_DESC]
      ) {
        count
        dimensions { clientIP clientAsn clientCountryName source action ruleId }
      }
    }
  }
}
```

- `clientIP` is where checks arrive from. `source` is the product that acted, which decides the fix in step 4. `ruleId` names the rule, when one of the person's rules acted.
- If the API rejects a filter or field, read its `errors`: drop that field, add `userAgent` to the dimensions instead of filtering on it, and pick out the `AllsWell/` rows yourself.
- **No events**: Cloudflare's protection didn't act. The 401 or 403 comes from the origin (the host's protection, HTTP basic auth, or a security plugin such as Wordfence), so hand over the monitor page's steps. A plugin behind Cloudflare sees Cloudflare's addresses instead of the checker's until it is set to read the visitor's address from `CF-Connecting-IP`; say so.
- The person can see the same in the dashboard under **Security, Analytics, Events**, filtered on a user agent that contains `AllsWell`.

## 3. Confirm the Addresses

Allow an address only when it is on the list the failing monitor's page in All's Well shows, or the person confirms it. Ask the person to copy that list. If the All's Well API reference (`${ALLS_WELL_URL:-https://alls-well.io}/docs/api.md`) documents an endpoint for the checkers' addresses, read them from there instead.

An address that sent the user agent but isn't on All's Well's list could be anyone. Show it to the person and leave it out.

Then choose where the addresses live:

| Choose | When |
|---|---|
| A set inline in the rule: `ip.src in {192.0.2.10 2001:db8::10}` | One zone, or the account has no room for another list |
| An account IP list named `agile_pixel_services`: `ip.src in $agile_pixel_services` | The account has several zones that All's Well monitors, so one change to the list covers them all. Free allows 1 list per account, Pro and Business 10 |

A list is created empty, with `{"name": "agile_pixel_services", "kind": "ip", "description": "Agile Pixel services"}`, and its items are added with `[{"ip": "192.0.2.10", "comment": "All's Well checker"}]`. Changes to items are asynchronous: wait until the `operation_id` they return reaches `completed` before a rule relies on them. An account can run one such operation at a time.

## 4. Choose the Fix

One skip rule handles every `source` except these (compare them without regard to case):

| `source` | What blocked | Fix |
|---|---|---|
| `botFight` | Bot Fight Mode, on Free | No rule can skip it: see below |
| `ip`, `ipRange`, `asn`, `country` | One of the person's IP Access rules | Show the person which one. It is their block to change |
| `l7ddos`, `validation` | DDoS protection, or a request Cloudflare treats as invalid | Nothing can allow these. Tell the person what you found |

The skip rule skips everything a custom rule can, so it keeps working when the person later turns on another product:

```json
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
```

| Part | Why |
|---|---|
| `ref` | A fixed name to find the rule by later, so running this again updates the rule instead of adding a second one |
| `expression` | The confirmed addresses (or `$agile_pixel_services`) and the user agent, together |
| `ruleset: "current"` | Skips the person's custom rules that come after it, including their challenge rules |
| `phases` | Skips rate limiting rules, WAF managed rules and Super Bot Fight Mode |
| `products` | Skips Zone Lockdown, User Agent Blocking, Browser Integrity Check, Hotlink Protection, and security level, which includes Under Attack mode |
| `logging` | Matches show in Security Events with the action `skip`, which is how you check the rule works |
| `position` | `"before": ""` puts the rule first. A skip affects only the rules after it |

**Bot Fight Mode** (`source` is `botFight`, or `fight_mode` is `true` in the zone's bot management settings) runs outside the rules engine, so no custom rule can skip it. Cloudflare doesn't apply it to a request that matches an IP Access rule, so add a zone IP Access rule for each confirmed address:

```json
{"mode": "whitelist", "configuration": {"target": "ip", "value": "192.0.2.10"}, "notes": "Agile Pixel services: All's Well checker"}
```

Use `"target": "ip6"` for an IPv6 address. This is broader than the skip rule: it lets that address past every custom rule, rate limit and managed rule on the zone. So use exact addresses, never ranges, and tell the person. If checks still fail with it in place, the remaining choices are the person's: turn Bot Fight Mode off, or move the zone to Pro, where Super Bot Fight Mode replaces it and the skip rule covers it. Don't turn it off yourself.

## 5. Validate, Show, Apply, Check

1. **Read** the zone's custom rules: the entry point ruleset of the `http_request_firewall_custom` phase. Note its `id`, and look for a rule whose `ref` is `agile_pixel_services`. A `404` means the zone has no custom rules yet.
2. **Validate** the write you're about to make with `dry_run=true` (`--validate-only` in `cf`). Cloudflare checks the expression, the plan's features, the rule quota (Free allows 5 custom rules, Pro 20, Business 100) and the list the rule names, and changes nothing. If it refuses a phase or product the plan doesn't have, take that one out and validate again.
3. **Show** the person the zone and the rule, with what it skips, and get a yes: the rule changes their site's security.
4. **Apply** the same write without `dry_run`:

   | The zone has | Write |
   |---|---|
   | The rule (found by `ref`) | Update that rule with the whole new rule |
   | Custom rules, but not this one | Add the rule to the ruleset |
   | No custom rules (`404`) | Create the ruleset: `{"name": "default", "kind": "zone", "phase": "http_request_firewall_custom", "rules": [<the rule without "position">]}` |

5. **Check**. After the monitor's next check, run step 2's query again: the checker's events now show the action `skip`. IP Access allows don't appear in Security Events, so for those, check the monitor instead. All's Well picks up again on its own at the next check that gets through.

If the project manages Cloudflare with Terraform (`cloudflare_ruleset` resources) or another tool, add the rule there instead: the next apply would remove a rule added through the API.

## 6. Hand Over What You Can't Do

When the person, or whoever owns the Cloudflare account, has to add it in the dashboard, give them these steps with the expression filled in:

1. Open the site in Cloudflare, then **Security, Security rules, Create rule, Custom rules**.
2. Name it `Agile Pixel services`, choose **Edit expression**, and paste the expression.
3. Choose the action **Skip**. Tick **All remaining custom rules**, **All rate limiting rules**, **All managed rules** and **All Super Bot Fight Mode rules**, and each product offered (Zone Lockdown, User Agent Blocking, Browser Integrity Check, Hotlink Protection, Security Level). Leave **Log matching requests** on.
4. Deploy it as the first rule.
5. On Free with Bot Fight Mode on: **Security rules, Create rule, IP access rules**, one per address, action **Allow**, for this website. The dashboard may offer IP access rules only once the zone has one; otherwise it takes the API request in `references/api.md`, with a token from whoever owns the account.

## Forbidden Patterns

| Don't | Do |
|---|---|
| Allow on the user agent alone | Match the addresses, with the user agent as an extra condition |
| Allow an address only because it sent the user agent | Only addresses on All's Well's list, or that the person confirms |
| Replace the entry point ruleset (`PUT …/phases/http_request_firewall_custom/entrypoint`, `cf rulesets entrypoint update`) | It replaces every custom rule on the zone. Add or update the one rule |
| Replace a list's items (`PUT …/items`) without its current items | It deletes the rest. Add new items and delete old ones by ID |
| Use an IP Access allow, or a range, where the skip rule works | The skip rule. IP Access only for Bot Fight Mode, and only exact addresses |
| Turn off Bot Fight Mode, Under Attack mode or one of the person's rules unasked | Explain the choices; the person decides |
| Apply a rule the person hasn't seen | Validate, show it, then apply |
| Take `cf … --dry-run` as validation | It only prints the request. `--validate-only` asks Cloudflare |
| Use the Global API Key, or commit a token | A scoped token in `CLOUDFLARE_API_TOKEN` |
| Put domains, IDs or addresses in `cf cli search` or `cf docs search` | Describe the task only |

## Quick Reference

| Question | Answer |
|---|---|
| Is Cloudflare in front? | `server: cloudflare` and `cf-ray`; a challenge adds `cf-mitigated: challenge` |
| The checker's user agent? | `AllsWell/1.0 AgileMonitor/1.0 (+https://alls-well.io)` |
| The checker's addresses? | The failing monitor's page in All's Well, matched with Security Events |
| Which phase? | `http_request_firewall_custom`; the rule's `ref` is `agile_pixel_services`, placed first |
| Bot Fight Mode? | No rule skips it: an IP Access allow per address, or the person turns it off |
| Validate without changing anything? | `?dry_run=true`, or `cf … --validate-only` |
| Custom rules per zone? | Free 5, Pro 20, Business 100 |
| Lists per account? | Free 1, Pro 10, Business 10 |
| Request recipes? | `references/mcp.md`, `references/cf-cli.md`, `references/api.md` |
