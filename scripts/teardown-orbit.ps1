param(
  [string]$Profile = 'orbit-lab',
  [string]$Region = 'us-east-1',
  [switch]$Confirm
)

$ErrorActionPreference = 'Stop'
if (-not $Confirm) {
  Write-Host 'This script deletes the orbit-midpoint CloudFormation stack and its DynamoDB table.'
  Write-Host 'Rerun with -Confirm only when you intend to delete the sandbox resources.'
  exit 0
}

aws cloudformation delete-stack --stack-name orbit-midpoint --region $Region --profile $Profile
Write-Host 'Deletion requested. Check CloudFormation before reusing the stack name.'
