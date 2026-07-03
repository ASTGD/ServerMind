<?php
/**
 * ServerAlly — WHMCS provisioning module (docs/WHMCS-INTEGRATION.md).
 *
 * Connects a WHMCS product ("ServerAlly Pro") to a ServerAlly deployment's
 * entitlement API. Billing events map to plan changes — nothing is ever deleted:
 *
 *   CreateAccount    -> plan = configured plan (default "pro"); provisions the
 *                       ServerAlly account if the email is new and stores the
 *                       one-time claim link in the service username field so it can
 *                       be shown in the client area / welcome email.
 *   SuspendAccount   -> plan = "free"   (invoice overdue)
 *   UnsuspendAccount -> plan = configured plan
 *   TerminateAccount -> plan = "free"   (cancelled; data stays)
 *   ChangePackage    -> plan = configured plan of the new product
 *
 * Install: copy this folder to <whmcs>/modules/servers/serverally/ and create a
 * product using the "ServerAlly" module. See the README for the full setup guide.
 */

if (!defined('WHMCS')) {
    die('This file cannot be accessed directly');
}

function serverally_MetaData()
{
    return [
        'DisplayName' => 'ServerAlly',
        'APIVersion' => '1.1',
        'RequiresServer' => false,
    ];
}

function serverally_ConfigOptions()
{
    return [
        'API URL' => [
            'Type' => 'text',
            'Size' => '60',
            'Default' => 'https://app.serverally.example',
            'Description' => 'Base URL of the ServerAlly deployment (no trailing slash)',
        ],
        'API Key' => [
            'Type' => 'password',
            'Size' => '60',
            'Description' => 'ENTITLEMENT_API_KEY from the ServerAlly backend .env',
        ],
        'Plan' => [
            'Type' => 'dropdown',
            'Options' => 'pro,free',
            'Default' => 'pro',
            'Description' => 'Plan this product activates',
        ],
    ];
}

/** One HTTPS call to the entitlement API. Returns [ok(bool), data(array)|error(string)]. */
function serverally_apiCall(array $params, string $method, string $path, ?array $body = null): array
{
    $base = rtrim(trim($params['configoption1']), '/');
    $key = trim($params['configoption2']);
    $url = $base . $path;

    $ch = curl_init($url);
    $headers = [
        'X-Entitlement-Key: ' . $key,
        'Content-Type: application/json',
        'Accept: application/json',
    ];
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 20,
        CURLOPT_HTTPHEADER => $headers,
        CURLOPT_CUSTOMREQUEST => $method,
    ]);
    if ($body !== null) {
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($body));
    }
    $raw = curl_exec($ch);
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curlErr = curl_error($ch);
    curl_close($ch);

    // Log with credentials masked (WHMCS Module Log).
    logModuleCall('serverally', $method . ' ' . $path, $body ?? [], $raw, '', [$key]);

    if ($raw === false) {
        return [false, 'Connection failed: ' . $curlErr];
    }
    $data = json_decode($raw, true) ?? [];
    if ($status >= 200 && $status < 300) {
        return [true, $data];
    }
    $detail = is_array($data) && isset($data['detail']) ? $data['detail'] : ('HTTP ' . $status);
    return [false, $detail];
}

/** Set the customer's plan. Returns 'success' or an error string (WHMCS contract). */
function serverally_setPlan(array $params, string $plan)
{
    $email = strtolower(trim($params['clientsdetails']['email']));
    [$ok, $data] = serverally_apiCall($params, 'POST', '/api/admin/entitlements/set', [
        'email' => $email,
        'plan' => $plan,
        'reference' => 'whmcs-service-' . ($params['serviceid'] ?? ''),
    ]);
    if (!$ok) {
        return 'ServerAlly API error: ' . $data;
    }
    // New account? Keep the one-time claim link on the service (username field) so the
    // client area and the welcome email template can show it.
    if (!empty($data['created']) && !empty($data['claim_url'])) {
        try {
            \WHMCS\Database\Capsule::table('tblhosting')
                ->where('id', $params['serviceid'])
                ->update(['username' => $data['claim_url']]);
        } catch (\Throwable $e) {
            // Non-fatal — the link is also in the Module Log.
        }
    }
    return 'success';
}

function serverally_CreateAccount(array $params)
{
    $plan = strtolower(trim($params['configoption3'] ?: 'pro'));
    return serverally_setPlan($params, $plan);
}

function serverally_SuspendAccount(array $params)
{
    return serverally_setPlan($params, 'free');
}

function serverally_UnsuspendAccount(array $params)
{
    $plan = strtolower(trim($params['configoption3'] ?: 'pro'));
    return serverally_setPlan($params, $plan);
}

function serverally_TerminateAccount(array $params)
{
    // Cancellation only drops the limits — the customer's account, servers and data
    // remain (pricing v2: the free plan includes every feature).
    return serverally_setPlan($params, 'free');
}

function serverally_ChangePackage(array $params)
{
    $plan = strtolower(trim($params['configoption3'] ?: 'pro'));
    return serverally_setPlan($params, $plan);
}

function serverally_TestConnection(array $params)
{
    [$ok, $data] = serverally_apiCall($params, 'GET', '/api/admin/entitlements/ping');
    return [
        'success' => $ok,
        'error' => $ok ? '' : ('ServerAlly: ' . $data),
    ];
}

/** Client area: open button + live usage, and the set-password link while unclaimed. */
function serverally_ClientArea(array $params)
{
    $base = rtrim(trim($params['configoption1']), '/');
    $email = strtolower(trim($params['clientsdetails']['email']));
    [$ok, $data] = serverally_apiCall($params, 'GET', '/api/admin/entitlements/' . rawurlencode($email));

    $html = '<div class="text-center" style="padding:12px 0">';
    if ($ok) {
        $html .= '<p>Plan: <strong>' . htmlspecialchars(ucfirst($data['plan'])) . '</strong>'
            . ' &nbsp;·&nbsp; Ally actions: ' . (int) $data['actions_used'] . ' / ' . (int) $data['actions_limit']
            . ' &nbsp;·&nbsp; Servers: ' . (int) $data['servers_used'] . ' / ' . (int) $data['servers_limit']
            . '</p>';
    }
    $claim = trim($params['username'] ?? '');
    if ($claim !== '' && strpos($claim, '/claim?token=') !== false) {
        $html .= '<a class="btn btn-success" href="' . htmlspecialchars($claim) . '" target="_blank">'
            . 'Set your password</a> &nbsp;';
    }
    $html .= '<a class="btn btn-primary" href="' . htmlspecialchars($base) . '" target="_blank">'
        . 'Open ServerAlly</a></div>';
    return $html;
}
