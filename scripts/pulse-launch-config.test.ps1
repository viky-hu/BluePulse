$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'pulse-launch-config.ps1')

function Assert-Allowed($name, $siteOrigin, $localWebOrigin, $quickTunnel, $apiOrigin, $localApiOrigin, $trustProxy) {
    try {
        Assert-PulseLaunchOriginConfiguration -SiteOrigin $siteOrigin -LocalWebOrigin $localWebOrigin `
            -QuickTunnel $quickTunnel -ApiOrigin $apiOrigin -LocalApiOrigin $localApiOrigin -TrustProxy $trustProxy
    } catch { throw "$name should have been accepted: $($_.Exception.Message)" }
}

function Assert-Rejected($name, $siteOrigin, $localWebOrigin, $quickTunnel, $apiOrigin, $localApiOrigin, $trustProxy) {
    try {
        Assert-PulseLaunchOriginConfiguration -SiteOrigin $siteOrigin -LocalWebOrigin $localWebOrigin `
            -QuickTunnel $quickTunnel -ApiOrigin $apiOrigin -LocalApiOrigin $localApiOrigin -TrustProxy $trustProxy
    } catch { return }
    throw "$name should have been rejected."
}

$localWeb = 'http://127.0.0.1:3000'
$localApi = 'http://127.0.0.1:8000'
Assert-Allowed 'local launcher defaults' $localWeb $localWeb '0' $localApi $localApi '0'
Assert-Allowed 'HTTPS Quick Tunnel origin' 'https://boats-genetics-publishers-retailer.trycloudflare.com' $localWeb '1' $localApi $localApi '0'

foreach ($origin in @(
    'http://boats-genetics-publishers-retailer.trycloudflare.com',
    'https://trycloudflare.com',
    'https://attacker.example',
    'https://demo.trycloudflare.com:8443',
    'https://demo.trycloudflare.com/path',
    'https://demo.trycloudflare.com/?x=1',
    'https://user@demo.trycloudflare.com'
)) {
    Assert-Rejected "invalid Quick Tunnel origin $origin" $origin $localWeb '1' $localApi $localApi '0'
}

Assert-Rejected 'Quick Tunnel opt-in is required for a public origin' 'https://demo.trycloudflare.com' $localWeb '0' $localApi $localApi '0'
Assert-Rejected 'API must remain loopback' 'https://demo.trycloudflare.com' $localWeb '1' 'http://192.168.1.10:8000' $localApi '0'
Assert-Rejected 'Quick Tunnel mode must not trust forwarded headers' 'https://demo.trycloudflare.com' $localWeb '1' $localApi $localApi '1'
Assert-Rejected 'unknown tunnel mode values are rejected' $localWeb $localWeb 'yes' $localApi $localApi '0'

Write-Output 'Pulse launcher origin configuration checks passed.'
