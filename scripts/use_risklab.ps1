# Dot-source from the repository root: . .\scripts\use_risklab.ps1
# Sets this PowerShell session only; does not modify provider files or global settings.
$projectRiskLabRoot = 'G:\.shortcut-targets-by-id\12TUCISuW6Nv0d0b2wOR-h_LdVWDMFjzq\data'
$projectRiskLabCatalog = Join-Path $projectRiskLabRoot '_catalog'
foreach ($projectRiskLabRequired in @(
    $projectRiskLabRoot,
    $projectRiskLabCatalog,
    (Join-Path $projectRiskLabCatalog 'data_paths.py'),
    (Join-Path $projectRiskLabCatalog 'catalog.csv'),
    (Join-Path $projectRiskLabCatalog 'intraday_inventory.csv.gz'),
    (Join-Path $projectRiskLabRoot 'bloomberg\inventory.csv')
)) {
    if (-not (Test-Path -LiteralPath $projectRiskLabRequired -ErrorAction Stop)) {
        throw "Required RiskLab path unavailable: $projectRiskLabRequired"
    }
}
$env:RISKLAB_DATA_ROOT = $projectRiskLabRoot
# Avoid writing __pycache__ when importing the provider's catalog utility.
$env:PYTHONDONTWRITEBYTECODE = '1'
Write-Output "RISKLAB_DATA_ROOT=$env:RISKLAB_DATA_ROOT"
Write-Output "Catalog=$projectRiskLabCatalog"
