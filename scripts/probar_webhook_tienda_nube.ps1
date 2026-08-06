param(
    [Parameter(Mandatory = $true)]
    [string]$Secret,

    [Parameter(Mandatory = $true)]
    [string]$StoreId,

    [Parameter(Mandatory = $true)]
    [string]$OrderId,

    [string]$Url = "http://127.0.0.1:8000/pedidos/webhooks/tienda-nube"
)

$payload = @{
    store_id = [long]$StoreId
    event    = "order/paid"
    id       = [long]$OrderId
}

# Debe firmarse exactamente el mismo cuerpo que se envía.
$body = $payload | ConvertTo-Json -Compress

$encoding = [System.Text.Encoding]::UTF8
$secretBytes = $encoding.GetBytes($Secret)
$bodyBytes = $encoding.GetBytes($body)

$hmac = [System.Security.Cryptography.HMACSHA256]::new($secretBytes)

try {
    $hashBytes = $hmac.ComputeHash($bodyBytes)
    $signature = [System.BitConverter]::ToString($hashBytes).Replace("-", "").ToLowerInvariant()
}
finally {
    $hmac.Dispose()
}

$headers = @{
    "x-linkedstore-hmac-sha256" = $signature
}

Write-Host "URL:" $Url
Write-Host "Payload:" $body
Write-Host "Firma calculada:" $signature

try {
    $response = Invoke-RestMethod `
        -Method Post `
        -Uri $Url `
        -ContentType "application/json" `
        -Headers $headers `
        -Body $body

    Write-Host "`nRespuesta:"
    $response | ConvertTo-Json -Depth 10
}
catch {
    Write-Host "`nError HTTP:"
    Write-Host $_.Exception.Message

    if ($_.ErrorDetails.Message) {
        Write-Host $_.ErrorDetails.Message
    }

    exit 1
}