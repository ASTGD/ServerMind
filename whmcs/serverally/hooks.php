<?php
/**
 * ServerAlly — nightly entitlement reconciliation (docs/SAAS-LAUNCH-PLAN.md §3.3).
 *
 * WHY THIS EXISTS
 *
 * The provisioning module only fires on Create/Suspend/Unsuspend/Terminate/ChangePackage.
 * A successful RENEWAL calls nothing — the customer was Pro and stays Pro. That is
 * correct, but it means the integration FAILS OPEN: if an event never lands (module
 * error, ServerAlly unreachable during the cron, a stopped WHMCS cron), the plan stays
 * wrong forever and silence looks exactly like success.
 *
 * The dangerous direction is the quiet one — a missed SUSPEND leaves a non-paying
 * customer on Pro, and nobody ever complains about getting too much.
 *
 * So once a night we send ServerAlly the full truth — every Active ServerAlly service's
 * email — and it makes plans match. Idempotent; nothing is ever deleted. Drift
 * self-heals within 24 hours.
 *
 * WHMCS auto-loads hooks.php from a module's folder, so installing the module installs
 * this. No crontab entry needed — it rides WHMCS's own daily cron.
 */

if (!defined('WHMCS')) {
    die('This file cannot be accessed directly');
}

use WHMCS\Database\Capsule;

/**
 * Reconcile ServerAlly plans against WHMCS's active services.
 * Returns a human-readable result line (also used by the admin "run now" path).
 */
function serverally_reconcile_run(bool $dryRun = false): string
{
    // Every product wired to this module. configoption1/2/3 = API URL / API Key / Plan.
    $products = Capsule::table('tblproducts')->where('servertype', 'serverally')->get();
    if (count($products) === 0) {
        return 'skipped: no products use the ServerAlly module';
    }

    // Assumption: all ServerAlly products point at ONE deployment. If you ever sell
    // against two, this needs grouping by API URL — it would silently reconcile the
    // wrong deployment otherwise.
    $first = $products[0];
    $base = rtrim(trim($first->configoption1), '/');
    $key = trim($first->configoption2);
    if ($base === '' || $key === '') {
        return 'skipped: the ServerAlly product has no API URL / API Key configured';
    }

    // Active services on a product whose plan is "pro" == our paying customers.
    // Anything else (Suspended, Terminated, Cancelled, Pending, Fraud) is not paying.
    $rows = Capsule::table('tblhosting')
        ->join('tblproducts', 'tblhosting.packageid', '=', 'tblproducts.id')
        ->join('tblclients', 'tblhosting.userid', '=', 'tblclients.id')
        ->where('tblproducts.servertype', 'serverally')
        ->where('tblhosting.domainstatus', 'Active')
        ->whereRaw('LOWER(TRIM(tblproducts.configoption3)) = ?', ['pro'])
        ->select('tblclients.email')
        ->get();

    $emails = [];
    foreach ($rows as $r) {
        $e = strtolower(trim($r->email));
        if ($e !== '') {
            $emails[$e] = true;   // dedupe: one client may hold two services
        }
    }
    $emails = array_keys($emails);

    $body = ['active_pro_emails' => $emails, 'dry_run' => $dryRun];

    $ch = curl_init($base . '/api/admin/entitlements/reconcile');
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 60,           // a full sweep is slower than a single set
        CURLOPT_CUSTOMREQUEST => 'POST',
        CURLOPT_POSTFIELDS => json_encode($body),
        CURLOPT_HTTPHEADER => [
            'X-Entitlement-Key: ' . $key,
            'Content-Type: application/json',
            'Accept: application/json',
        ],
    ]);
    $raw = curl_exec($ch);
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curlErr = curl_error($ch);
    curl_close($ch);

    logModuleCall('serverally', 'POST /reconcile', $body, $raw, '', [$key]);

    if ($raw === false) {
        // Cannot reach ServerAlly — say so loudly. A quiet failure here is the exact
        // problem this job exists to solve.
        $msg = 'ServerAlly reconcile FAILED (cannot reach): ' . $curlErr;
        logActivity($msg);
        return $msg;
    }

    $data = json_decode($raw, true) ?? [];

    if ($status === 409) {
        // The blast-radius guard fired: ServerAlly refused because the list would
        // downgrade too many customers at once. That means THIS query is probably
        // wrong — never auto-retry with force. A human must look.
        $d = $data['detail'] ?? [];
        $msg = sprintf(
            'ServerAlly reconcile REFUSED — would downgrade %s of %s Pro customers '
                . '(limit %s). The active-service list is probably wrong. Investigate '
                . 'before forcing.',
            $d['would_downgrade'] ?? '?',
            $d['total_pro'] ?? '?',
            $d['allowed_without_force'] ?? '?'
        );
        logActivity($msg);
        return $msg;
    }

    if ($status < 200 || $status >= 300) {
        $detail = is_array($data) && isset($data['detail'])
            ? (is_string($data['detail']) ? $data['detail'] : json_encode($data['detail']))
            : ('HTTP ' . $status);
        $msg = 'ServerAlly reconcile FAILED: ' . $detail;
        logActivity($msg);
        return $msg;
    }

    $up = count($data['upgraded'] ?? []);
    $down = count($data['downgraded'] ?? []);
    $unknown = count($data['unknown'] ?? []);
    $msg = sprintf(
        'ServerAlly reconcile%s: %d active pro, %d upgraded, %d downgraded, %d unknown',
        $dryRun ? ' (dry run)' : '',
        count($emails), $up, $down, $unknown
    );

    // Only shout when something actually drifted. A clean run every night is noise —
    // and noise is how a real drift alert gets ignored.
    if ($up || $down || $unknown) {
        // A dry run CHANGED NOTHING — saying "corrected" would tell an operator the
        // drift is dealt with when it is still there.
        logActivity($msg . ($dryRun ? ' — drift DETECTED (dry run: nothing was changed).'
                                    : ' — drift corrected.')
            . ' Upgraded: ' . implode(', ', $data['upgraded'] ?? [])
            . ' | Downgraded: ' . implode(', ', $data['downgraded'] ?? [])
            . ' | Unknown (in WHMCS, no ServerAlly account): '
            . implode(', ', $data['unknown'] ?? []));
    }
    return $msg;
}

add_hook('DailyCronJob', 1, function ($vars) {
    try {
        serverally_reconcile_run(false);
    } catch (\Throwable $e) {
        // Never let this break WHMCS's daily cron — other jobs must still run.
        logActivity('ServerAlly reconcile crashed: ' . $e->getMessage());
    }
});
