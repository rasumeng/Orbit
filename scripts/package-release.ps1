param(
  [Parameter(Mandatory = $true)]
  [string]$ReleaseId
)

$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'package_release.py'
python $script --release-id $ReleaseId
if ($LASTEXITCODE -ne 0) {
  throw 'Release packaging failed. Review the error above; no AWS resources were changed.'
}
