# Orbit

Orbit is a student life management dashboard we're developing for our Cloud Computing course at the University of Texas at Arlington. The idea came from how easy it is to lose track of responsibilities when you're balancing classes, work, projects, and other commitments. We wanted to build a single place to organize those responsibilities while learning how to develop and deploy a cloud-based application using AWS.

## What Orbit does

The current version lets us:

- Create responsibilities with a title, category, priority, and optional due date.
- View responsibilities sorted by due date, including completed items.
- Filter the list by category.
- Mark responsibilities as completed or pending.
- Store the data in DynamoDB so it remains available after refreshing the dashboard.

The frontend is a React and TypeScript application. The backend is a Python Lambda function that exposes the health and responsibility endpoints. The current midpoint scope does not include user accounts, automatic Canvas synchronization, reminders, or a publicly hosted frontend.

## Architecture

```text
React/Vite frontend
        |
        v
Local FastAPI proxy -- AWS SigV4 --> IAM-protected Lambda Function URL
                                            |
                                            v
                                      DynamoDB table
```

The browser talks only to the local FastAPI proxy. The proxy signs requests with AWS Signature Version 4 using the local AWS credential chain, so AWS credentials never enter browser code. The Lambda function uses the `OrbitItems` DynamoDB table, and CloudWatch provides the usual Lambda logs.

We originally planned to use API Gateway, but AWS Academy restrictions prevented that approach in our sandbox. The deployed version uses a Lambda Function URL with `AWS_IAM` authentication instead.

## Project structure

```text
backend/                 Lambda handler and local FastAPI proxy
frontend/                React, TypeScript, and Vite dashboard
scripts/                 Repeatable deployment and teardown helpers
docs/                    Midpoint evaluation notes
template.yaml            AWS SAM/CloudFormation infrastructure
```

## Prerequisites

- Node.js 20 or newer
- Python 3.12 recommended for matching the Lambda runtime
- AWS CLI v2
- AWS SAM CLI
- An AWS Academy profile with temporary credentials

The deployment scripts use the `orbit-lab` AWS profile by default. AWS Academy credentials expire when a lab session ends, and a new session may use a different AWS account. The account ID, role ARN, and Lambda Function URL should therefore be supplied at deployment time rather than committed to the repository.

## Run locally

The frontend uses `http://127.0.0.1:8000` as the proxy URL by default. From the repository root, install the proxy dependencies and start it:

```powershell
..\venv\Scripts\python.exe -m pip install -r backend\proxy-requirements.txt
$env:ORBIT_LAMBDA_URL = 'https://REPLACE_WITH_CURRENT_FUNCTION_URL'
$env:AWS_REGION = 'us-east-1'
..\venv\Scripts\python.exe -m uvicorn backend.proxy:app --host 127.0.0.1 --port 8000
```

The proxy needs valid temporary AWS credentials in the normal AWS credential chain. Do not put access keys, session tokens, or credentials in `.env` files or source code.

In a second terminal:

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). The frontend's `VITE_API_URL` should point to the local proxy, not directly to AWS.

## Deploy to a fresh AWS Academy account

The SAM template creates the `OrbitItems` DynamoDB table, the `OrbitBackend` Python 3.12 Lambda function, and an IAM-protected Lambda Function URL. It accepts an existing Lambda execution role ARN because AWS Academy accounts may restrict IAM role creation and role-policy changes.

First validate and build without changing AWS resources:

```powershell
.\scripts\deploy-orbit.ps1 `
  -Profile orbit-lab `
  -Region us-east-1 `
  -ExecutionRoleArn arn:aws:iam::CURRENT_ACCOUNT_ID:role/lambda-run-role
```

When the dry run succeeds, deploy explicitly:

```powershell
.\scripts\deploy-orbit.ps1 `
  -Profile orbit-lab `
  -Region us-east-1 `
  -ExecutionRoleArn arn:aws:iam::CURRENT_ACCOUNT_ID:role/lambda-run-role `
  -Deploy
```

The script verifies the active account, runs `sam validate --lint`, builds the Lambda package, and prints the new Function URL after deployment. Update `ORBIT_LAMBDA_URL` with that value before starting the local proxy.

The template normally attaches a narrowly scoped DynamoDB resource-based policy for the Lambda role. If the sandbox denies `dynamodb:PutResourcePolicy`, use `-TableResourcePolicyEnabled false` and apply the equivalent table policy through the permitted AWS workflow. The deployment script does not modify IAM policies automatically.

To remove the sandbox stack, use the opt-in teardown helper:

```powershell
.\scripts\teardown-orbit.ps1 -Profile orbit-lab -Region us-east-1
.\scripts\teardown-orbit.ps1 -Profile orbit-lab -Region us-east-1 -Confirm
```

## API routes

The Lambda API currently supports:

- `GET /health` → `{ "status": "ok", "service": "orbit" }`
- `GET /items` → `{ "items": [...], "truncated": false }`
- `POST /items` with `title`, `category`, `priority`, and optional `dueAt`
- `PATCH /items/{id}` with `{ "status": "completed" }` or `{ "status": "pending" }`

Due dates must be ISO 8601 timestamps with a timezone when provided. Responsibilities without a due date are accepted and displayed as `No due date`.

## Current limitations

- The data is shared in one demonstration table; there is no user or tenant separation.
- Listing uses a DynamoDB scan with a 100-item limit and does not provide pagination.
- There is no deletion route in the current application.
- Canvas ICS import, automatic feed synchronization, reminders, and Cognito authentication are planned ideas, not implemented features.
- The frontend is currently run locally for the course demonstration.

## Midpoint status

We have tested the main end-to-end flow: creating a responsibility, retrieving it after refresh, and changing its status. The project also includes repeatable SAM/CloudFormation deployment instructions so the infrastructure can be recreated when an AWS Academy sandbox account changes. See [docs/MIDPOINT_EVALUATION.md](docs/MIDPOINT_EVALUATION.md) for the project summary, challenges, and presentation plan.
