# Wiring heartbeats

A heartbeat monitor goes down when its job hasn't requested the ping URL within the check interval. Request the URL after the job **succeeds**, so a failing job goes quiet and alerts. GET, HEAD and POST all count; the body is ignored.

`apply --env-file .alls-well.env` writes each URL into that file as `ALLS_WELL_PING_<NAME>`; it never prints them (from the monitor's name in the manifest: "Nightly backup" becomes `ALLS_WELL_PING_NIGHTLY_BACKUP`). Read it from the environment; never write the URL into the repository.

Use `curl -fsS --retry 3 --max-time 10 -o /dev/null` so a slow or failed ping never breaks the job and retries a blip.

## Laravel scheduler

```php
// config/services.php
'alls_well' => ['pings' => [
    'nightly_backup' => env('ALLS_WELL_PING_NIGHTLY_BACKUP'),
    'fulfilment_sync' => env('ALLS_WELL_PING_FULFILMENT_SYNC'),
]],

// routes/console.php
use Illuminate\Support\Facades\Schedule;

Schedule::command('backup:run')->dailyAt('02:00')
    ->pingOnSuccessIf(filled($url = config('services.alls_well.pings.nightly_backup')), $url);
```

`pingOnSuccessIf` skips the ping where the variable is empty, so environments without it are unaffected; keep production's URLs out of local `.env` files. A failed ping is logged and never fails the task. Pinging needs Guzzle, which Laravel ships with. Use `config()`, not `env()`, so it works with `config:cache`.

While a heartbeat is paused, its pings get a `404`, which the scheduler logs. Switch it on right after deploying.

### Queued jobs

When the job implements `ShouldQueue`, `Schedule::job(new PruneCarts)` only dispatches it; a ping from the scheduler proves the dispatch, not that a worker ran it. Ping from the end of the job's `handle()` instead. (A job without `ShouldQueue` runs inside the scheduler, so `pingOnSuccessIf` on the schedule is enough.)

```php
public function handle(): void
{
    // ... the work ...

    // A failed ping must never fail the job: retry() throws by default, and the queue would run the work again.
    if ($url = config('services.alls_well.pings.prune_carts')) {
        rescue(fn () => Http::timeout(10)->retry(3, 1000, throw: false)->get($url), report: false);
    }
}
```

A heartbeat on a frequently scheduled queued job also tells you the queue worker is alive.

If the job's class isn't in the repository (a package, or another service), leave its heartbeat paused and hand the snippet over to whoever owns the job.

## crontab

```cron
0 2 * * * /usr/local/bin/backup.sh && curl -fsS --retry 3 --max-time 10 -o /dev/null "$ALLS_WELL_PING_BACKUP"
```

Cron doesn't read `.env`: set the variable at the top of the crontab, or in the script.

## systemd timer

```ini
# backup.service
[Service]
Type=oneshot
EnvironmentFile=/etc/northwind/alls-well.env
ExecStart=/usr/local/bin/backup.sh
ExecStartPost=/usr/bin/curl -fsS --retry 3 --max-time 10 -o /dev/null ${ALLS_WELL_PING_BACKUP}
```

`ExecStartPost` runs only when `ExecStart` succeeded.

## GitHub Actions schedule

```yaml
on:
  schedule:
    - cron: '0 3 * * *'
jobs:
  nightly:
    runs-on: ubuntu-latest
    steps:
      - run: ./scripts/nightly.sh
      - name: Tell All's Well the job ran
        if: success()
        run: curl -fsS --retry 3 --max-time 10 -o /dev/null "${{ secrets.ALLS_WELL_PING_NIGHTLY }}"
```

Scheduled workflows can start late or be skipped under load: give the monitor a generous interval. Store the URL as a repository secret, never in the workflow file.

## Node.js

```js
await runImport();
await fetch(process.env.ALLS_WELL_PING_IMPORT, { method: 'POST', signal: AbortSignal.timeout(10_000) });
```

## WordPress

WP-Cron only runs when someone visits the site. For a job that must run on time, run WP-Cron from the system cron and ping after it:

```cron
*/15 * * * * cd /var/www/site && wp cron event run --due-now --quiet && curl -fsS --retry 3 --max-time 10 -o /dev/null "$ALLS_WELL_PING_WP_CRON"
```

To watch a WordPress site as a whole (updates, plugins, health), use the All's Well plugin instead: see `manual-steps.md`.

## Containers and Kubernetes

Put the ping in the job's command, after the work, and pass the URL as a secret:

```yaml
containers:
  - name: backup
    image: northwind/backup:1.4
    command: ["sh", "-c", "backup && wget -q -O /dev/null \"$ALLS_WELL_PING_BACKUP\""]
    envFrom:
      - secretRef:
          name: alls-well-pings
```

## Choosing the interval

There is no grace period: the monitor is down the moment the interval passes without a ping.

| Job runs | Takes up to | Interval |
|---|---|---|
| Every 15 minutes | 2 minutes | `check_interval_minutes: 30` |
| Hourly | 20 minutes | `check_interval_seconds: 5400` |
| Daily | 1 hour | `check_interval_seconds: 90000` |
| Weekly | 2 hours | `check_interval_seconds: 612000` |

Use `check_interval_minutes` when the interval is exactly 1, 5, 15, 30 or 60 minutes, and `check_interval_seconds` otherwise. Each must be at least the plan's minimum: `min_interval_minutes` and `min_interval_seconds` from `GET /team`.
