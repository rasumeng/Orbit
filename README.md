# Orbit — Student Life Command Center

CSE 4333 Cloud Computing midpoint prototype. Manage school, work, leadership, projects, and personal responsibilities in one unified dashboard.

## Scope

Midpoint: create responsibilities, view them sorted by due date, mark complete; persisted in AWS DynamoDB via API Gateway + Python Lambda. Dashboard is React/TypeScript. Canvas ICS one-time import is **not included** in this starter and is a stretch goal.

## Architecture

React (local Vite) -> Amazon API Gateway HTTP API -> Python Lambda -> DynamoDB. AWS CloudWatch captures Lambda logs. AWS SAM/CloudFormation defines backend resources.

## Prerequisites

AWS CLI configured with deploy permissions, AWS SAM CLI, Python 3.12, Node.js 20+. Lab accounts might deny IAM/CloudFormation resource creation: verify permissions first.

## Deploy backend

```bash
sam validate
sam build
sam deploy --guided
```

Use `us-east-1` if that's the course region and note the `ApiUrl` output. **This demo has no authentication. Do not publish its URL or use real personal, academic, or work records.** For a shared/public deployment, add authentication/authorization first. Remove demo data/resources when done.

## Run frontend

```bash
cd frontend
cp .env.example .env   # On Windows PowerShell: Copy-Item .env.example .env
# Edit .env and set VITE_API_URL to deployed SAM ApiUrl
npm install
npm run dev
```

Open http://localhost:5173. If browser CORS fails, ensure you are using this URL and redeploy the SAM template after changes. Don't commit the .env file.

## API contract

- `GET /health` -> `{ "status": "ok", "service": "orbit" }`
- `GET /items` -> `{ "items": [...], "truncated": false }` (first 100 items; midpoint demo only)
- `POST /items` -> create record with `{title,category,dueAt,priority}`
- `PATCH /items/{id}` -> `{ "status": "completed" }` or `pending`

Categories: `school`, `work`, `leadership`, `projects`, `personal`.

## Example API smoke test

```bash
curl "$API_URL/health"
curl -X POST "$API_URL/items" -H "Content-Type: application/json" -d '{"title":"Cloud project demo","category":"school","priority":"high","dueAt":"2026-10-16T22:00:00Z"}'
curl "$API_URL/items"
```

## Midpoint evidence

Capture: SAM/CloudFormation deployed stack, DynamoDB record, API response, Lambda CloudWatch logs, and working dashboard. Record creating an item, refreshing, completing it, and verifying AWS persistence.

## Not yet implemented

Canvas ICS import; automatic feed sync; Cognito auth; reminders; multi-user tenant isolation; pagination. Do not claim these are implemented.

## Security & scaling limitations

Unauthenticated HTTP routes are intentionally **demo only**. API Gateway CORS does not provide access control. GET currently uses a DynamoDB Scan with a 100-item limit and no pagination, appropriate only for small demonstration data; future per-user queries need a userId partition key and authenticated API. Do not accept arbitrary calendar URLs in a Lambda downloader without an allowlist and SSRF defenses; treat feed URLs as secrets.
