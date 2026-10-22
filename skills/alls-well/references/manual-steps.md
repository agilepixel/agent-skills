# Steps only a person can do

These parts of All's Well have no API, so an agent can't do them. Give the person each step that applies, with the project's own names filled in. Paths are relative to the All's Well base URL (default `https://alls-well.io`). Most need an Owner or Admin of the team.

## Connect a server

The server agent reports disk usage, services, packages and reboots, and alerts when the server stops reporting.

1. Open **Servers**, then **Add server** (`/servers/create`). Name it after the host (for example `shop-prod-1`) and pick how often it reports. The team's plan sets how many servers it can add and how often they can report (see `/pricing`).
2. The server's page shows one install command, of this shape:

   ```bash
   curl -fsSL https://alls-well.io/agent/install.sh | sudo bash -s -- --url "https://alls-well.io/agent/<server token>" --interval 300
   ```

3. Run it on the server as root. It needs Linux (or another Unix) with bash, curl and cron, and sends a first report straight away.
4. Re-running the same command updates the agent. `... | sudo bash -s -- --uninstall` removes it.

The URL in the command is that server's credential: don't commit it.

## Connect WordPress sites

The plugin reports WordPress, plugin and theme versions, available updates and site health.

1. Install the plugin on each site from the WordPress.org directory: **Plugins, Add New**, search for "All's Well", or run `wp plugin install alls-well --activate`. WordPress.org then serves its updates. You can also deploy it with the site's code, from https://wordpress.org/plugins/alls-well/ or `/downloads/alls-well-wordpress.zip`.
2. Connect a site with the button (plugin 1.4 or later). A WordPress administrator does this in a browser:
   1. In WordPress, open **Settings, All's Well** and click **Connect to All's Well**. Until the site connects, a notice on the Dashboard offers the same button.
   2. Sign in to All's Well, or create a free account there and confirm the email address.
   3. Choose the team (you must be its Owner or an Admin) and, if you like, who gets alerts. Then click **Connect site**.
   4. WordPress shows "Connected", and the site appears under **Sites**. Nothing is copied by hand.
3. For many sites, or sites set up from code or a deploy script, use the team enrolment key instead:
   1. On **Sites** (`/sites`), under **Connect many sites**, create the team enrolment key (`amk_…`). It is shown once and can only add sites.
   2. Give it to each site, in any one of these ways:

      ```php
      // wp-config.php, kept out of version control or read from the environment
      define( 'ALLS_WELL_KEY', 'amk_…' );
      ```

      ```bash
      wp alls-well connect amk_…
      ```

      Or paste it under **Connect with a site token or enrolment key instead** in **Settings, All's Well**.
   3. With the constant, the site registers itself on its next page load.
4. The team's plan sets how many sites it can connect (see `/pricing`). Past that, connecting is refused until an Owner upgrades or a site is removed; reconnecting a site the team already has always works.
5. Connecting a new site also adds an `http` monitor on its home page and an `ssl` monitor, unless the team already has one of that kind on the same host or the plan has no room left. They are named after the site, not with the project's prefix, so the sync neither adopts nor prunes them: don't add the same checks to the manifest, or the site is checked twice. `list-monitors` shows them. A site that misses three reports in a row also goes down and alerts the team.

## Status page and badges

1. **Status pages, New status page** (`/status-pages/create`): name it, make it public, and add the monitors customers care about.
2. For a custom domain such as `status.example.com`, add the two DNS records the edit page shows: a CNAME to the All's Well host and a TXT record at `_alls-well.status.example.com`. Then click **Verify domain**.
3. A badge works only for a monitor on a public status page. Its ID is in the API (`GET /api/v1/monitors`):

   ```markdown
   [![Storefront status](https://alls-well.io/badge/48213)](https://alls-well.io/status/northwind)
   ```

## Maintenance windows

**Maintenance** (`/maintenance-windows`) skips checks for one monitor, or all of the team's, between two times. Use it for planned downtime. A zero-downtime deploy doesn't need one; a deploy that runs `php artisan down` does. To pause a single monitor from a script instead, set `"is_active": false` in the manifest and apply, or call `POST /api/v1/monitors/{id}/toggle`.

## Let checks through bot protection

If checks fail with 401, 403 or 429 while the site works in a browser, a WAF, Cloudflare or the host's bot protection is blocking them. The failing monitor's page in All's Well names the provider and lists the IP addresses checks come from.

- Allow-list those IP addresses, or
- allow the user agent `AllsWell/1.0 AgileMonitor/1.0 (+https://alls-well.io)`.

## Production secrets

Set these wherever the app, its scheduler and CI run, never in the repository:

- `ALLS_WELL_PING_*`: from the `.alls-well.env` file that `apply --env-file .alls-well.env` writes
- every `${VAR}` the manifest uses (webhook URLs, bot tokens, basic-auth passwords)
- `ALLS_WELL_TOKEN`, only where the sync runs (a developer's machine or a CI secret)

## Replace a token

Tokens don't expire. To replace one, for example after it was shared: create a new token in **Settings, API tokens**, switch every place that uses it, then revoke the old one.
