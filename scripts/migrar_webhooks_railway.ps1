# Migracion segura y reversible de webhooks de pedidos Tiendanube a Railway.
# Por defecto solo PREVISUALIZA. Agregar -Apply para realizar PUT.
# Ejecutar solo DESPUES de desplegar WEB y WORKER y comprobar firma HMAC.
param(
    [string]$StoreId = '1545642',
    [string]$UrlRailway = 'https://gbptnsync-production.up.railway.app/pedidos/webhooks/tienda-nube',
    [switch]$Apply,
    [switch]$IncludeLegacy
)
$ErrorActionPreference = 'Stop'
$token = Read-Host 'Access token de Tiendanube (no compartir)'
$headers = @{
    Authentication = "bearer $token"
    'User-Agent' = 'IntegradorGBP-TN/1.0'
    'Content-Type' = 'application/json'
}
$base = "https://api.tiendanube.com/v1/$StoreId/webhooks"
# Lista cerrada: impide alterar webhooks de terceros o eventos futuros por error.
$expected = @{
    '38630329' = 'order/paid'
    '38809677' = 'order/created'
    '38809678' = 'order/updated'
    '38809679' = 'order/paid'
    '38809680' = 'order/packed'
    '38809681' = 'order/fulfilled'
    '38809682' = 'order/cancelled'
    '38809683' = 'order/edited'
    '38809684' = 'order/pending'
    '38809685' = 'order/voided'
    '38809686' = 'order/unpacked'
}
$renderHosts = @('gbp-tn-sync.onrender.com','appmercadolibre-eplm.onrender.com')
$hooks = @(Invoke-RestMethod -Method Get -Uri $base -Headers $headers)
$changed = @()
foreach ($id in ($expected.Keys | Sort-Object)) {
    $matches = @($hooks | Where-Object { [string]$_.id -eq [string]$id })
    if ($matches.Count -ne 1) { throw "Webhook ID $id no encontrado o duplicado. No continuar." }
    $hook = $matches[0]
    if ($hook.event -ne $expected[$id]) { throw "Evento inesperado para $id. No continuar." }
    if ($hook.url -eq $UrlRailway) {
        Write-Host "OK: $id $($hook.event) ya apunta a Railway"
        continue
    }
    if ($id -ne '38630329' -and -not $IncludeLegacy) {
        Write-Host "OMITIDO (usar -IncludeLegacy): $id $($hook.event) $($hook.url)"
        continue
    }
    $uri = [Uri]$hook.url
    if ($uri.Host -notin $renderHosts) {
        throw "Host inesperado para $id : $($uri.Host). No continuar."
    }
    Write-Host "PLAN: $id $($hook.event): $($hook.url) -> $UrlRailway"
    if ($Apply) {
        $body = @{ event=$hook.event; url=$UrlRailway } | ConvertTo-Json
        Invoke-RestMethod -Method Put -Uri "$base/$id" -Headers $headers -Body $body | Out-Null
        $check = Invoke-RestMethod -Method Get -Uri "$base/$id" -Headers $headers
        if ($check.url -ne $UrlRailway -or $check.event -ne $hook.event) {
            throw "Fallo de verificacion del webhook $id. Inspeccionar antes de continuar."
        }
        $changed += $id
        Write-Host "VERIFICADO: $id"
    }
}
if (-not $Apply) {
    Write-Host 'MODO PREVISUALIZACION: No se ha modificado ningun webhook.'
    Write-Host 'Para migrar los antiguos, validar primero WEB/WORKER y usar -Apply -IncludeLegacy.'
} else {
    Write-Host "Modificados y verificados: $($changed -join ', ')"
}
