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
Local FastAPI proxy -- SigV4/AWS_IAM --> Lambda Function URL
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
- IAM-protected Lambda Function URL with SigV4 requests from the local proxy.
- SAM validation and build workflow with account-specific execution role parameters.
- CloudFormation outputs for the Function URL, table name, and function name.

The API routes tested for the midpoint are `GET /health`, `GET /items`, `POST /items`, and `PATCH /items/{id}`. Deletion is not implemented or claimed as part of the current scope.

## AWS deployment approach

Our first design used API Gateway, but AWS Academy restrictions prevented us from creating the required API Gateway resources. We changed the backend to use a Lambda Function URL with `AWS_IAM` authentication. The React application still avoids direct AWS access: the local FastAPI proxy signs requests and forwards them to Lambda.

The Lambda execution role is passed into the SAM deployment because Academy accounts do not consistently allow projects to create roles or attach policies. The role used by our Lambda did not initially have DynamoDB access. We addressed that by using a narrowly scoped DynamoDB table resource-based policy for the data operations required by Orbit. The template includes a fallback parameter for accounts where `dynamodb:PutResourcePolicy` is not available.

AWS Academy sandbox accounts also change between lab sessions. Our original deployment belonged to a previous account and was not available in the next session. We adopted SAM and CloudFormation so the table, Lambda function, Function URL, and outputs can be recreated instead of relying on manual console configuration.

During validation, we fixed two infrastructure issues: Function URL CORS did not accept `OPTIONS` in the configured method list, and the DynamoDB policy created a circular dependency by referencing the table ARN from inside the table definition. The policy now constructs the ARN from the known table name.

## Current limitations and remaining work

- The current table is a shared demonstration dataset with no user accounts or tenant isolation.
- Listing uses a DynamoDB scan limited to 100 records and has no pagination.
- There is no delete operation.
- Canvas ICS import, automatic synchronization, reminders, and Cognito authentication remain future work.
- The frontend is run locally rather than hosted as a public site.
- AWS Academy credentials expire and must be refreshed for future sessions.

## Midpoint demonstration plan

1. Explain the problem of responsibilities being spread across school, work, projects, and personal commitments.
2. Show the React dashboard and the local proxy architecture.
3. Create a responsibility with a category, priority, and optional deadline.
4. Refresh the page to show that the record persisted in DynamoDB.
5. Mark the responsibility completed and show the updated dashboard counts.
6. Show the Lambda Function URL, CloudFormation/SAM deployment output, DynamoDB record, and CloudWatch logs.
7. Explain the AWS Academy restrictions, the Function URL/SigV4 solution, and future work such as Canvas import and authentication.

The presentation should use actual screenshots and logs from the deployed sandbox rather than describing features that are not implemented.
