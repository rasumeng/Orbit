param(
  [string]$Profile = 'orbit-lab',
  [string]$Region = 'us-east-1',
  [Parameter(Mandatory = $true)]
  [string]$ExecutionRoleArn,
  [ValidateSet('true', 'false')]
  [string]$TableResourcePolicyEnabled = 'true',
  [switch]$Deploy
)

$ErrorActionPreference = 'Stop'

function Require-Command([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "$Name was not found on PATH. Install/configure the AWS CLI and SAM CLI first."
  }
}

Require-Command 'aws'
Require-Command 'sam'

$identity = aws sts get-caller-identity --profile $Profile --output json | ConvertFrom-Json
if (-not $identity.Account) { throw 'Unable to determine the active AWS account.' }
$configuredRegion = aws configure get region --profile $Profile
Write-Host "AWS account: $($identity.Account)"
Write-Host "AWS ARN:     $($identity.Arn)"
Write-Host "AWS region:  $Region (profile default: $configuredRegion)"
Write-Host "Role ARN:    $ExecutionRoleArn"

if ($identity.Account -eq '571487732810') {
  Write-Warning 'This is the previous Orbit sandbox account, not the current account supplied for this session.'
}

sam validate --lint --region $Region
if ($LASTEXITCODE -ne 0) {
  throw 'SAM validation failed. Build/deployment was not started.'
}

sam build --region $Region
if ($LASTEXITCODE -ne 0) {
  throw 'SAM build failed. Deployment was not started.'
}

if (-not $Deploy) {
  Write-Host ''
  Write-Host 'Validation/build complete. No AWS resources were changed.'
  Write-Host 'Review the generated changes, then rerun with -Deploy to create/update the stack.'
  exit 0
}

sam deploy `
  --stack-name orbit-midpoint `
  --region $Region `
  --profile $Profile `
  --capabilities CAPABILITY_IAM `
  --resolve-s3 `
  --parameter-overrides "ExecutionRoleArn=$ExecutionRoleArn" "TableResourcePolicyEnabled=$TableResourcePolicyEnabled" `
  --no-confirm-changeset `
  --no-fail-on-empty-changeset

$functionUrl = aws cloudformation describe-stacks --stack-name orbit-midpoint --region $Region --profile $Profile --query "Stacks[0].Outputs[?OutputKey=='FunctionUrl'].OutputValue" --output text
$tableName = aws cloudformation describe-stacks --stack-name orbit-midpoint --region $Region --profile $Profile --query "Stacks[0].Outputs[?OutputKey=='TableName'].OutputValue" --output text
Write-Host "Function URL: $functionUrl"
Write-Host "Table name:   $tableName"
Write-Host 'Set AWS_PROFILE and AWS_REGION before starting backend.proxy; the local proxy invokes the function by name.'
