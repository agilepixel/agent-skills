# Agile Pixel agent skills

Skills that teach AI coding agents, such as Claude Code, Codex and Cursor, to work with [Agile Pixel](https://agilepixel.io)'s products.

| Skill | What it does |
|---|---|
| [`alls-well`](skills/alls-well/SKILL.md) | Sets up uptime, SSL certificate and heartbeat monitoring with [All's Well](https://alls-well.io) for the project the agent is working in, and keeps the setup in the repository as `alls-well.json`. [Docs](https://alls-well.io/docs/api/agent-skill) |

## Install

**Claude Code**, as a plugin:

```
/plugin marketplace add agilepixel/agent-skills
/plugin install alls-well@agile-pixel-products
```

**Any agent**, with the [skills CLI](https://skills.sh):

```bash
npx skills add agilepixel/agent-skills --skill alls-well
```

**Without either**, each product serves its own skill. For All's Well:

```bash
curl -fsSL https://alls-well.io/docs/api/skill/install.sh | bash
```

## Where the files come from

Don't edit the files under `skills/` here. Each skill is maintained in its product's repository, next to the API it describes, and the product serves it from its own site. Every hour the **Sync skills** workflow copies each skill from there, so this repository matches the live product. Any edit made here is overwritten by the next sync. To report a problem with a skill, contact the product: hello@alls-well.io for All's Well.

### Adding a product's skill

1. Serve the skill from the product: a `files.txt` listing every file's path, one per line, with each file under the same base URL.
2. Add a line to `.github/skill-sources.txt`: the skill's name, then that base URL. The skill's `SKILL.md` must have that same `name`.
3. Add a plugin entry to `.claude-plugin/marketplace.json` with `"source": "./"`, `"strict": false` and `"skills": ["./skills/<name>"]`, then run `claude plugin validate .`
4. Run **Sync skills** from the Actions tab, and add the skill to the table above.

GitHub pauses scheduled workflows in a public repository after 60 days without a commit, and emails the owners when it does. If no skill has changed for that long, turn **Sync skills** back on in the Actions tab.

## Licence

[MIT](LICENSE)
