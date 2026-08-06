$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()


function Invoke-ControlCalidad {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Nombre,

        [Parameter(Mandatory = $true)]
        [scriptblock]$Comando
    )

    Write-Host "== $Nombre ==" -ForegroundColor Cyan

    & $Comando

    if ($LASTEXITCODE -ne 0) {
        throw "$Nombre falló con código de salida $LASTEXITCODE."
    }
}

Invoke-ControlCalidad `
    -Nombre "Ruff lint" `
    -Comando {
        python -m ruff check app tests
    }

Invoke-ControlCalidad `
    -Nombre "Ruff format" `
    -Comando {
        python -m ruff format --check app tests
    }

Invoke-ControlCalidad `
    -Nombre "Compilación" `
    -Comando {
        python -m compileall -q app tests
    }

Invoke-ControlCalidad `
    -Nombre "Pruebas" `
    -Comando {
        python -m pytest -q
    }

Write-Host ""
Write-Host "Calidad validada correctamente." -ForegroundColor Green