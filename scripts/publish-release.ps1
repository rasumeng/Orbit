param(
  [Parameter(Mandatory = $true)] [string]$ReleaseId,
  [Parameter(Mandatory = $true)] [string]$ArtifactBucket,
  [string]$Region = 'us-east-1',
  [string]$Profile = ''
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$releaseDir = Join-Path $repo "artifacts\releases\$ReleaseId"
$manifestPath = Join-Path $releaseDir 'release.json'

if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
  throw "Release manifest not found at $manifestPath. Run scripts/package-release.ps1 first."
}

python (Join-Path $PSScriptRoot 'package_release.py') --validate-only --release-dir $releaseDir --release-id $ReleaseId
if ($LASTEXITCODE -ne 0) { throw 'Local release validation failed; nothing was uploaded.' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.releaseId -ne $ReleaseId) { throw 'Release ID does not match the release manifest.' }

$awsArgs = @()
if ($Profile) { $awsArgs += @('--profile', $Profile) }
if ($Region) { $awsArgs += @('--region', $Region) }
$prefix = "releases/$ReleaseId/"

# A release prefix is immutable. Listing failure is treated as an error, never as empty.
$existingJson = & aws s3api list-objects-v2 --bucket $ArtifactBucket --prefix $prefix --max-keys 1 @awsArgs --output json
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the artifact bucket. Check AWS Academy credentials and S3 ListBucket permission.' }
$existing = $existingJson | ConvertFrom-Json
if ($existing.Contents -and $existing.Contents.Count -gt 0) {
  throw "Release prefix s3://$ArtifactBucket/$prefix already contains objects. Choose a new ReleaseId; published release paths are immutable."
}

foreach ($file in @('orbit-backend.zip', 'orbit-frontend.zip', 'orbit-stack.yaml', 'release.json')) {
  $path = Join-Path $releaseDir $file
  $key = "$prefix$file"
  & aws s3 cp $path "s3://$ArtifactBucket/$key" --checksum-algorithm SHA256 @awsArgs
  if ($LASTEXITCODE -ne 0) { throw "Upload failed for $key. Use a new ReleaseId for a clean retry." }
  Write-Host "Published s3://$ArtifactBucket/$key"
}

$templateUrl = "https://s3.$Region.amazonaws.com/$ArtifactBucket/$prefix" + 'orbit-stack.yaml'
Write-Host ''
Write-Host 'CloudFormation template URL:'
Write-Host $templateUrl
Write-Host 'BackendZipKey:' $manifest.backendZipKey
Write-Host 'FrontendZipKey:' $manifest.frontendZipKey
Write-Host 'ArtifactVersion:' $ReleaseId
Write-Host 'Artifact publication complete. No CloudFormation stack was changed.'
