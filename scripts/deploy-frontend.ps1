
param(
    [string]$Profile = 'orbit-lab',
    [string]$Region = 'us-east-1',
    [string]$StackName = 'orbit-frontend'
)

$ErrorActionPreference = 'Stop'

$frontendDir = (Resolve-Path (Join-Path $PSScriptRoot '..\frontend')).Path

# 1. Discover AWS resources from CloudFormation
Write-Host "Discovering frontend resources..."

$bucket = aws cloudformation describe-stacks `
    --stack-name $StackName `
    --profile $Profile `
    --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" `
    --output text

if ($LASTEXITCODE -ne 0 -or -not $bucket -or $bucket -eq 'None') {
    throw "Could not find the frontend S3 bucket."
}

$distribution = aws cloudformation describe-stacks `
    --stack-name $StackName `
    --profile $Profile `
    --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" `
    --output text

if ($LASTEXITCODE -ne 0 -or -not $distribution -or $distribution -eq 'None') {
    throw "Could not find the CloudFront distribution."
}

# 2. Build the React frontend
Write-Host "Building Orbit frontend..."

Push-Location $frontendDir

try {
    npm ci
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed."
    }

    npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend build failed."
    }
}
finally {
    Pop-Location
}

# 3. Upload the build to S3
Write-Host "Uploading frontend to S3..."

aws s3 sync (Join-Path $frontendDir 'dist') "s3://$bucket" `
    --delete `
    --profile $Profile `
    --region $Region

if ($LASTEXITCODE -ne 0) {
    throw "S3 upload failed."
}

# 4. Invalidate CloudFront cache
Write-Host "Invalidating CloudFront cache..."

aws cloudfront create-invalidation `
    --distribution-id $distribution `
    --paths "/*" `
    --profile $Profile `
    --region $Region

if ($LASTEXITCODE -ne 0) {
    throw "CloudFront invalidation failed."
}

Write-Host "Orbit frontend deployment submitted successfully!"
