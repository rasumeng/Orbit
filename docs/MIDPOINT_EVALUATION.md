# Orbit Midpoint Evaluation

## Project problem

Students often keep responsibilities in several places: course systems, calendars, project notes, work schedules, and personal reminders. Orbit is our attempt to bring those responsibilities into one simple dashboard while giving us hands-on experience building and deploying a cloud application.

## Proposed solution

Orbit lets a user create responsibilities, assign a category and priority, optionally add a deadline, and mark items completed or pending. The dashboard keeps pending and completed items together, shows deadline information when available, and stores the records in DynamoDB.

## Current architecture

```text
React + TypeScript + Vite
             |
             v
Local FastAPI proxy -- AWS SDK / IAM --> Lambda Invoke API
                                             |
                                             v
                                          DynamoDB
```

The Lambda function runs Python 3.12. AWS SAM and CloudFormation define the Lambda function, Function URL, DynamoDB table, and outputs. CloudWatch provides Lambda logs. The local proxy is bound to `127.0.0.1` and keeps AWS credentials out of the browser.

## Implemented and tested

- React dashboard with category filtering and summary counts.
- Create responsibility flow.
- Retrieve and sort responsibilities by due date.
- Mark a responsibility completed or pending.
- Optional due dates, including compatibility with existing records that do not contain `dueAt`.
- DynamoDB persistence across page refreshes.
- IAM-authorized local proxy invoking Lambda through the AWS SDK; the template also provisions an IAM-protected Function URL.
- SAM validation and build workflow with account-specific execution role parameters.
- CloudFormation outputs for the Function URL, table name, and function name.
- Apple, Google, and Canvas `.ics` import UI and Lambda endpoint are implemented in the current branch. The importer parses files locally and uses event IDs to avoid duplicates and refresh changed details; Google Calendar ZIP exports must be extracted first.
- Project spaces support create/join invite codes, shared membership names, project-scoped tasks, optional teammate assignment, editable descriptions/due dates, and a mini calendar.
- A generated Orbit workspace access code opens the same workspace on another device. Personal responsibilities and imports are scoped to that workspace; project work is shared with workspaces that join using the project invite code.

The API routes tested for the midpoint are `GET /health`, `GET /items`, `POST /items`, and `PATCH /items/{id}`. Deletion is not implemented or claimed as part of the current scope.

## AWS deployment approach

Our first design used API Gateway, but AWS Academy restrictions prevented us from creating the required API Gateway resources. Orbit uses a local FastAPI proxy with the AWS SDK to invoke Lambda using the student's temporary IAM credentials. The React application avoids direct AWS access. The template also provisions a Lambda Function URL with `AWS_IAM` authentication for architecture demonstrations.

The Lambda execution role is passed into the SAM deployment because Academy accounts do not consistently allow projects to create roles or attach policies. The role used by our Lambda did not initially have DynamoDB access. We addressed that by using a narrowly scoped DynamoDB table resource-based policy for the data operations required by Orbit. The template includes a fallback parameter for accounts where `dynamodb:PutResourcePolicy` is not available.

AWS Academy sandbox accounts also change between lab sessions. Our original deployment belonged to a previous account and was not available in the next session. We adopted SAM and CloudFormation so the table, Lambda function, Function URL, and outputs can be recreated instead of relying on manual console configuration.

During validation, we fixed two infrastructure issues: Function URL CORS did not accept `OPTIONS` in the configured method list, and the DynamoDB policy created a circular dependency by referencing the table ARN from inside the table definition. The policy now constructs the ARN from the known table name.

## Current limitations and remaining work

- The current table is a shared demonstration dataset with no user accounts or tenant isolation.
- Project spaces are a collaboration prototype, not a security boundary: any user with access to this shared demo can read its spaces and tasks. Authentication and project-level authorization remain necessary before real student data is used.
- Listing uses a DynamoDB scan limited to 100 records and has no pagination.
- There is no delete operation.
- Calendar `.ics` import uses the deployed Lambda endpoint; imported event files still need a live end-to-end demonstration for this checkpoint.
- Automatic calendar-feed synchronization, reminders, code recovery, and stronger identity authentication remain future work. Orbit access codes are bearer credentials and must be kept private.
- The frontend is run locally rather than hosted as a public site.
- AWS Academy credentials expire and must be refreshed for future sessions.

## Midpoint demonstration plan

1. Explain the problem of responsibilities being spread across school, work, projects, and personal commitments.
2. Show the React dashboard and the local proxy architecture.
3. Create a responsibility with a category, priority, and optional deadline.
4. Refresh the page to show that the record persisted in DynamoDB.
5. Mark the responsibility completed and show the updated dashboard counts.
6. Show the Lambda Function URL, CloudFormation/SAM deployment output, DynamoDB record, and CloudWatch logs.
7. Demonstrate importing a calendar `.ics` file (Apple, Google, or Canvas); explain future work such as automatic synchronization and stronger identity authentication.

The presentation should use actual screenshots and logs from the deployed sandbox rather than describing features that are not implemented.
