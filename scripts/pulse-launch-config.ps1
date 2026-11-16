function Assert-PulseLaunchOriginConfiguration {
    param(
        [Parameter(Mandatory)][string]$SiteOrigin,
        [Parameter(Mandatory)][string]$LocalWebOrigin,
        [Parameter(Mandatory)][string]$QuickTunnel,
        [Parameter(Mandatory)][string]$ApiOrigin,
        [Parameter(Mandatory)][string]$LocalApiOrigin,
        [Parameter(Mandatory)][string]$TrustProxy
    )

    if ($QuickTunnel -cnotin @('0', '1')) {
        throw 'BLUEPULSE_QUICK_TUNNEL must be 0 or 1.'
    }
    if ($ApiOrigin -cne $LocalApiOrigin) {
        throw 'The local launcher requires BLUEPULSE_API_URL to match its loopback API address.'
    }
    if ($TrustProxy -cne '0') {
        throw 'Proxy trust is unavailable in the local launcher.'
    }

    if ($QuickTunnel -eq '1') {
        if ($SiteOrigin -cnotmatch '^https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com$') {
            throw 'Quick Tunnel mode requires BLUEPULSE_SITE_ORIGIN to be the exact HTTPS trycloudflare.com origin.'
        }
        return
    }

    if ($SiteOrigin -cne $LocalWebOrigin) {
        throw 'The local launcher requires BLUEPULSE_SITE_ORIGIN to match its loopback Web address.'
    }
}
