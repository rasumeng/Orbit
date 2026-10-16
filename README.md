# Orbit

Orbit is a student life management dashboard we're developing for our Cloud Computing course at the University of Texas at Arlington. The idea came from how easy it is to lose track of responsibilities when you're balancing classes, work, projects, and other commitments. We wanted to build a single place to organize those responsibilities while learning how to develop and deploy a cloud-based application using AWS.

## What Orbit does

The current version lets us:

- Create responsibilities with a title, category, priority, and optional due date.
- View responsibilities sorted by due date, including completed items.
- Filter the list by category.
- Mark responsibilities as completed or pending.
- Store the data in DynamoDB so it remains available after refreshing the dashboard.
- Import Apple, Google, or Canvas calendar events from one or more downloaded `.ics` files. Re-imports skip events already in Orbit.
- Create project spaces, invite classmates with a code, join a space, and group or assign tasks to teammates.

The frontend is a React and TypeScript application. The backend is a Python Lambda function that exposes health, responsibility, and project-space endpoints. Project spaces are a course-demo collaboration feature: the current prototype has no sign-in or membership-based access controls, so anyone with access to the shared AWS-backed demo can see its spaces and tasks. Do not put private student information in it.

## Architecture

```text
React/Vite frontend
        |
        v
Local FastAPI proxy -- AWS SDK / IAM --> Orbit Lambda (Invoke API)
                                            |
                                            v
                                      DynamoDB table
```

The browser talks only to the local FastAPI proxy. The proxy invokes Lambda with the local AWS credential chain, so AWS credentials never enter browser code. The Lambda function uses the `OrbitItems` DynamoDB table, and CloudWatch provides the usual Lambda logs. An IAM-protected Function URL is also provisioned for the architecture demonstration.

To import a calendar, export or download its `.ics` file and select **Import Calendar** in Orbit. Apple Calendar can export a calendar as `.ics`; Google Calendar's export is a ZIP, so extract it and select one or more `.ics` files. Canvas calendar feeds can also be downloaded as `.ics`. Parsing happens in the browser; Orbit receives event titles, dates, and identifiers, not account credentials or private feed URLs. Matching event IDs update changed titles/due dates and skip unchanged events. This is a file import, not automatic account synchronization.

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

The deployment scripts use the `orbit-lab` AWS profile by default. AWS Academy credentials expire when a lab session ends, and a new session may use a different AWS account. The account ID and role ARN should therefore be supplied at deployment time rather than committed to the repository.

## Run locally

The frontend uses `http://127.0.0.1:8000` as the proxy URL by default. From the repository root, install the proxy dependencies and start it:

```powershell
..\venv\Scripts\python.exe -m pip install -r backend\proxy-requirements.txt
$env:AWS_PROFILE = 'orbit-lab'
$env:AWS_REGION = 'us-east-1'
..\venv\Scripts\python.exe -m uvicorn backend.proxy:app --host 127.0.0.1 --port 8000
```

The proxy needs valid temporary AWS credentials in the selected AWS profile. By default it invokes the `OrbitBackend` Lambda; set `ORBIT_FUNCTION_NAME` only if your deployed function uses another name. Do not put access keys, session tokens, or credentials in `.env` files or source code.

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

The script verifies the active account, runs `sam validate --lint`, builds the Lambda package, and prints the Function URL and table name after deployment. The local proxy invokes the function by its configured function name.

The template normally attaches a narrowly scoped DynamoDB resource-based policy for the Lambda role. If the sandbox denies `dynamodb:PutResourcePolicy`, use `-TableResourcePolicyEnabled false` and apply the equivalent table policy through the permitted AWS workflow. The deployment script does not modify IAM policies automatically.

To remove the sandbox stack, use the opt-in teardown helper:

```powershell
.\scripts\teardown-orbit.ps1 -Profile orbit-lab -Region us-east-1
.\scripts\teardown-orbit.ps1 -Profile orbit-lab -Region us-east-1 -Confirm
```

## API routes

Create an Orbit space to receive a 24-character access code. Keep it private and save it: it is the credential used to open the same space on another device, and there is no account-recovery flow. After opening a space, the frontend sends the code in the `x-orbit-access-code` header for workspace data requests. Personal responsibilities and calendar imports are scoped to that space; project responsibilities are shared with workspaces that joined the project invite code.

The Lambda API currently supports:

- `GET /health` → `{ "status": "ok", "service": "orbit" }`
- `POST /spaces` to create a workspace and return its access code once
- `POST /spaces/open` with an access code and `GET /spaces/me` to open and validate a workspace
- `GET /items`, `POST /items`, `POST /items/import`, and `PATCH /items/{id}` require the workspace access code
- `GET /projects`, `POST /projects`, and `POST /projects/join` require the workspace access code; project invite codes let another workspace join a shared team space
- `PATCH /items/{id}` supports status, assignee, title, description, and due-date updates

Due dates must be ISO 8601 timestamps with a timezone when provided. Responsibilities without a due date are accepted and displayed as `No due date`.

## Current limitations

- Orbit access codes are bearer credentials: anyone who has a code can open that workspace. Codes are not recoverable if lost, and there is no email-based identity or rate limiting yet.
- Project invite codes allow anyone who has one to join that team space; there are no member roles or removal controls yet.
- Listing uses a DynamoDB scan with a 100-item limit and does not provide pagination.
- There is no deletion route in the current application.
- Apple, Google, and Canvas `.ics` file import is supported; automatic account synchronization, reminders, and Cognito authentication are not implemented.
- Calendar events are parsed in the browser. Orbit sends event titles, due dates, and stable event identifiers through the local AWS proxy; it does not store calendar feed URLs.
- The frontend is currently run locally for the course demonstration.

## Midpoint status

We have tested the main end-to-end flow: creating a responsibility, retrieving it after refresh, and changing its status. The project also includes repeatable SAM/CloudFormation deployment instructions so the infrastructure can be recreated when an AWS Academy sandbox account changes. See [docs/MIDPOINT_EVALUATION.md](docs/MIDPOINT_EVALUATION.md) for the project summary, challenges, and presentation plan.
