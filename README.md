# Agile Pixel agent skills

Skills that teach AI coding agents, such as Claude Code, Codex and Cursor, to work with [Agile Pixel](https://agilepixel.io)'s products.

| Skill | What it does |
|---|---|
| [`alls-well`](skills/alls-well/SKILL.md) | Sets up uptime, SSL certificate and heartbeat monitoring with [All's Well](https://alls-well.io) for the project the agent is working in. It keeps the setup in the repository as `alls-well.json`, files the monitors under the codebase's All's Well project, and checks that each new monitor proves itself before its contacts are alerted. [Docs](https://alls-well.io/docs/api/agent-skill) |
| [`cloudflare-allowlist`](skills/cloudflare-allowlist/SKILL.md) | Lets Agile Pixel's services, starting with All's Well's uptime checks, through Cloudflare's WAF and bot protection when All's Well reports a monitor as `blocked` ("Bot protection is blocking these checks"). It finds the checker's addresses in Cloudflare's Security Events and adds one skip rule, through the Cloudflare MCP server, the `cf` CLI or the API |

## Install

**Claude Code**, as a plugin. The `alls-well` plugin includes both skills:

```
/plugin marketplace add agilepixel/agent-skills
/plugin install alls-well@agile-pixel-products
```

**Any agent**, with the [skills CLI](https://skills.sh):

```bash
npx skills add agilepixel/agent-skills --skill alls-well
npx skills add agilepixel/agent-skills --skill cloudflare-allowlist
```

**Without either**, each product serves its own skill. For All's Well:

```bash
curl -fsSL https://alls-well.io/docs/api/skill/install.sh | bash
```

## Where the files come from

A skill for one product is maintained in that product's repository, next to the API it describes, and the product serves it from its own site. Every hour the **Sync skills** workflow copies each skill listed in `.github/skill-sources.txt` from there, so this repository matches the live product. Don't edit those skills here (today, `skills/alls-well`): any edit is overwritten by the next sync. To report a problem with one, contact the product: hello@alls-well.io for All's Well.

A skill that spans Agile Pixel's products, such as `cloudflare-allowlist`, is maintained here. The sync never touches a skill that isn't in `.github/skill-sources.txt`, so edit it in this repository like any other file.

### Adding a product's skill

1. Serve the skill from the product: a `files.txt` listing every file's path, one per line, with each file under the same base URL.
2. Add a line to `.github/skill-sources.txt`: the skill's name, then that base URL. The skill's `SKILL.md` must have that same `name`.
3. Add a plugin entry to `.claude-plugin/marketplace.json` with `"source": "./"`, `"strict": false` and `"skills": ["./skills/<name>"]`, then run `claude plugin validate .`
4. Run **Sync skills** from the Actions tab, and add the skill to the table above.

GitHub pauses scheduled workflows in a public repository after 60 days without a commit, and emails the owners when it does. If no skill has changed for that long, turn **Sync skills** back on in the Actions tab.

## Licence

[MIT](LICENSE)
