# The Cloudflare API MCP Server

Each step of `SKILL.md` through Cloudflare's MCP server for its whole API, at `https://mcp.cloudflare.com/mcp`. Cloudflare's other MCP servers (Workers bindings, observability, documentation and so on) can't change WAF rules; use this one.

## Connecting

In Claude Code:

```bash
claude mcp add --transport http cloudflare-api https://mcp.cloudflare.com/mcp
```

Then the person runs `/mcp` and signs in. Cloudflare asks which permissions to grant: those `SKILL.md` lists, for the account that holds the zone. When a call needs a permission the connection lacks, the server asks the client to sign in again with it added. For an unattended run, the server also takes a Cloudflare API token as a bearer token; an account token needs **Account Resources, Read** as well. Tokens restricted to client IP addresses don't work with it.

## How It Works

| Tool | Use |
|---|---|
| `search` | Runs JavaScript against the API's OpenAPI document (`spec.paths`) to find an operation |
| `execute` | Runs JavaScript that calls `cloudflare.request({method, path, body})` and returns what you choose |
| `docs` | Searches Cloudflare's documentation |
| `whoami` | Shows which user or account the connection belongs to |

Each `search` and `execute` result is cut to about 6,000 tokens, so return only the fields you need, as below. Put query parameters such as `dry_run=true` in `path`. `cloudflare.request` returns the API's whole response: `{success, errors, result}`.

## The zone

```js
async () => {
  const r = await cloudflare.request({ method: "GET", path: "/zones?name=example.com" });
  return r.result.map((z) => ({ id: z.id, name: z.name, plan: z.plan?.legacy_id, account: z.account?.id }));
}
```

```js
async () => {
  const r = await cloudflare.request({ method: "GET", path: "/zones/<ZONE_ID>/bot_management" });
  return { fight_mode: r.result?.fight_mode, errors: r.errors };
}
```

## Security Events (step 2)

The server sends GraphQL requests to the Analytics API when the path is `/client/v4/graphql`:

```js
async () => {
  const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
  const r = await cloudflare.request({
    method: "POST",
    path: "/client/v4/graphql",
    body: {
      query: `query ($zoneTag: string, $since: Time) {
        viewer { zones(filter: { zoneTag: $zoneTag }) {
          firewallEventsAdaptiveGroups(
            filter: { datetime_geq: $since, userAgent_like: "AllsWell/%" }
            limit: 25, orderBy: [count_DESC]
          ) { count dimensions { clientIP clientAsn clientCountryName source action ruleId } }
        } }
      }`,
      variables: { zoneTag: "<ZONE_ID>", since },
    },
  });
  return r;
}
```

## An IP list (step 3)

```js
async () => {
  const account = "<ACCOUNT_ID>";
  const lists = await cloudflare.request({ method: "GET", path: `/accounts/${account}/rules/lists` });
  return lists.result.map(({ id, name, kind, num_items }) => ({ id, name, kind, num_items }));
}
```

Create it with `POST /accounts/<ACCOUNT_ID>/rules/lists` and `{"name": "agile_pixel_services", "kind": "ip", "description": "Agile Pixel services"}`, then add the confirmed addresses and wait for the operation to finish:

```js
async () => {
  const account = "<ACCOUNT_ID>", list = "<LIST_ID>";
  const added = await cloudflare.request({
    method: "POST",
    path: `/accounts/${account}/rules/lists/${list}/items`,
    body: [{ ip: "192.0.2.10", comment: "All's Well checker" }],
  });
  if (!added.success) return added.errors;
  for (let i = 0; i < 20; i++) {
    const op = await cloudflare.request({
      method: "GET",
      path: `/accounts/${account}/rules/lists/bulk_operations/${added.result.operation_id}`,
    });
    if (op.result.status === "completed" || op.result.status === "failed") return op.result;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return { status: "still running", operation_id: added.result.operation_id };
}
```

Never `PUT` the list's items: it replaces all of them. To remove one, `DELETE` the items path with `{"items": [{"id": "<item id>"}]}`.

## The skip rule (steps 4 and 5)

Read the zone's custom rules. A `404` in the result means the zone has none yet:

```js
async () => {
  const r = await cloudflare.request({
    method: "GET",
    path: "/zones/<ZONE_ID>/rulesets/phases/http_request_firewall_custom/entrypoint",
  });
  if (!r.success) return r.errors;
  return {
    ruleset_id: r.result.id,
    rules: r.result.rules.map(({ id, ref, description, action, enabled }) => ({ id, ref, description, action, enabled })),
  };
}
```

Then make the write that matches what you found, first with `DRY_RUN` set to `true`. Show the person the rule, and only after they agree run it again with `DRY_RUN` set to `false`:

```js
async () => {
  const DRY_RUN = true;
  const zone = "<ZONE_ID>", ruleset = "<RULESET_ID or empty>", existing = "<RULE_ID or empty>";
  const rule = {
    ref: "agile_pixel_services",
    description: "Agile Pixel services: let All's Well uptime checks through",
    expression: '(ip.src in {192.0.2.10 2001:db8::10} and http.user_agent contains "AllsWell/")',
    action: "skip",
    action_parameters: {
      ruleset: "current",
      phases: ["http_ratelimit", "http_request_firewall_managed", "http_request_sbfm"],
      products: ["zoneLockdown", "uaBlock", "bic", "hot", "securityLevel"],
    },
    logging: { enabled: true },
    position: { before: "" },
  };
  const q = DRY_RUN ? "?dry_run=true" : "";
  let r;
  if (existing) {
    r = await cloudflare.request({ method: "PATCH", path: `/zones/${zone}/rulesets/${ruleset}/rules/${existing}${q}`, body: rule });
  } else if (ruleset) {
    r = await cloudflare.request({ method: "POST", path: `/zones/${zone}/rulesets/${ruleset}/rules${q}`, body: rule });
  } else {
    const { position, ...first } = rule;
    r = await cloudflare.request({
      method: "POST",
      path: `/zones/${zone}/rulesets${q}`,
      body: { name: "default", kind: "zone", phase: "http_request_firewall_custom", rules: [first] },
    });
  }
  return { dry_run: DRY_RUN, success: r.success, errors: r.errors };
}
```

Never `PUT` the entry point ruleset: it replaces every custom rule on the zone.

## An IP Access rule for Bot Fight Mode (step 4)

One per confirmed address, after the person has seen them (there is no `dry_run` here):

```js
async () => {
  const zone = "<ZONE_ID>";
  const existing = await cloudflare.request({
    method: "GET",
    path: `/zones/${zone}/firewall/access_rules/rules?notes=Agile%20Pixel%20services`,
  });
  const have = new Set(existing.result.map((rule) => rule.configuration.value));
  const results = [];
  for (const ip of ["192.0.2.10"]) {
    if (have.has(ip)) continue;
    const r = await cloudflare.request({
      method: "POST",
      path: `/zones/${zone}/firewall/access_rules/rules`,
      body: {
        mode: "whitelist",
        configuration: { target: ip.includes(":") ? "ip6" : "ip", value: ip },
        notes: "Agile Pixel services: All's Well checker",
      },
    });
    results.push({ ip, success: r.success, errors: r.errors });
  }
  return results;
}
```
