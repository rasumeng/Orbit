# Orbit

**A Serverless Student Life Management Dashboard Built on AWS**

Orbit is a cloud-based student responsibility management application developed for **CSE 4333 – Cloud Computing** at the University of Texas at Arlington.

The project addresses the challenge of managing responsibilities across academics, employment, leadership, personal commitments, and collaborative projects through a centralized dashboard.

Beyond its application features, Orbit demonstrates the design, deployment, integration, and management of cloud infrastructure using Amazon Web Services (AWS).

The application is deployed entirely on AWS using a serverless architecture. Users access Orbit through Amazon CloudFront, while AWS Lambda handles backend operations and Amazon DynamoDB provides persistent storage.

The current website URL is available from the unified CloudFormation stack's `WebsiteURL` output. The URL changes when the stack is recreated.

## Features

Orbit currently supports:

- **Responsibility Management:** Create responsibilities with titles, categories, priorities, and optional due dates.
- **Task Tracking:** View, filter, edit, and mark responsibilities as pending or completed.
- **Persistent Cloud Storage:** Store responsibilities in Amazon DynamoDB so changes remain available after refreshing the application.
- **Calendar Import:** Import events from downloaded Apple Calendar, Google Calendar, and Canvas `.ics` files. Re-importing updates changed events and skips unchanged entries.
- **Personal Workspaces:** Create a workspace with a unique access code and reopen it across devices.
- **Collaborative Projects:** Create shared project spaces, generate invitation codes, join projects, and assign responsibilities to teammates.
- **Cloud-Based Access:** Access the application through a public HTTPS endpoint without hosting the frontend or backend locally.

## AWS Architecture

Orbit follows a serverless architecture designed to separate frontend hosting, backend processing, and data persistence.

```text
                      User's Browser
                            |
                            | HTTPS
                            v
                    Amazon CloudFront
                     /             \
                    /               \
             Static Content       /api/*
                   |                 |
                   v                 v
              Amazon S3       Lambda Function URL
           (Private Bucket)    (AWS IAM + OAC)
                                     |
                                     v
                                 AWS Lambda
                                 (Python 3.12)
                                     |
                                     v
                               Amazon DynamoDB
                                 (OrbitItems)

                     AWS CloudWatch Logs
                       (Lambda Monitoring)

                  AWS CloudFormation + SAM
                   (Infrastructure as Code)
```

### AWS Services

| AWS Service                                | Role in Orbit                                                                                         |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| **Amazon CloudFront**                      | Provides the public HTTPS endpoint and routes requests to the appropriate frontend or backend origin. |
| **Amazon S3**                              | Stores the compiled React application in a private bucket.                                            |
| **AWS Lambda**                             | Executes the Python backend without requiring dedicated servers.                                      |
| **Amazon DynamoDB**                        | Provides persistent NoSQL storage for workspaces, responsibilities, and projects.                     |
| **AWS IAM**                                | Manages service permissions and protects the Lambda Function URL.                                     |
| **CloudFront Origin Access Control (OAC)** | Allows CloudFront to securely access private S3 content and sign requests to the Lambda Function URL. |
| **Amazon CloudWatch**                      | Captures Lambda execution logs for monitoring and troubleshooting.                                    |
| **AWS CloudFormation**                     | Provisions and manages infrastructure through declarative templates.                                  |
| **AWS SAM**                                | Builds and deploys the serverless backend using CloudFormation.                                       |

### Request Flow

1. A user navigates to Orbit's public CloudFront URL.
2. CloudFront retrieves the React application from a private Amazon S3 bucket.
3. The browser renders the frontend and sends API requests to `/api/*` on the same CloudFront domain.
4. CloudFront routes API requests to the Lambda Function URL and signs the origin requests using AWS Signature Version 4.
5. AWS Lambda receives the request and executes the appropriate Python backend logic.
6. Lambda reads or writes application records in DynamoDB.
7. The response returns through CloudFront to the browser.
8. Lambda execution information is available through CloudWatch Logs.

### Architecture Decisions

**Serverless Compute**

AWS Lambda eliminates the need to provision and maintain dedicated backend servers. Compute resources are managed by AWS and invoked in response to API requests.

**NoSQL Storage**

DynamoDB was selected for its managed, serverless design and ability to store application records without operating a traditional database server. Orbit uses the `OrbitItems` table with a string partition key named `id`.

**CloudFront and Private S3 Hosting**

The React application is compiled into static assets and stored in Amazon S3. CloudFront provides HTTPS delivery and restricts direct access to the private bucket through Origin Access Control.

**IAM-Protected API**

The backend uses a Lambda Function URL with `AWS_IAM` authentication. CloudFront signs origin requests so browser clients do not need AWS credentials.

**Infrastructure as Code**

CloudFormation and SAM templates define the infrastructure, allowing it to be recreated in another AWS account rather than relying exclusively on manual console configuration.

**AWS Academy Compatibility**

API Gateway was initially considered for backend routing. However, the AWS Academy Learner Lab environment restricted the required API Gateway operations.

The final architecture uses CloudFront with an IAM-protected Lambda Function URL as an alternative that works within the available AWS permissions.

## Project Structure

```text
Orbit/
├── backend/
│   ├── app.py
│   └── ...
├── frontend/
│   ├── src/
│   ├── package.json
│   ├── package-lock.json
│   └── .env.production
├── scripts/
│   ├── package-release.ps1
│   ├── package_release.py
│   ├── publish-release.ps1
│   └── teardown-orbit.ps1
├── docs/
│   └── MIDPOINT_EVALUATION.md
├── template.yaml
├── orbit-stack.yaml
├── orbit-frontend-template.yaml
└── README.md
```

### Infrastructure Files

| File                           | Purpose                                                                                    |
| ------------------------------ | ------------------------------------------------------------------------------------------ |
| `orbit-stack.yaml`             | Unified CloudFormation template for Lambda, DynamoDB, private S3, CloudFront, and API access. |
| `template.yaml`                | Legacy SAM backend template; retained for reference, not used by the unified release workflow. |
| `orbit-frontend-template.yaml` | Legacy split frontend template; retained for reference, not used by the unified release workflow. |
| `scripts/package-release.ps1`  | Builds and validates immutable versioned release artifacts locally. |
| `scripts/publish-release.ps1`  | Publishes artifacts under a unique S3 release prefix using AWS CLI credentials. |
| `scripts/teardown-orbit.ps1`   | Legacy SAM-stack teardown helper; it does not delete the unified stack.                      |
| `frontend/.env.production`     | Configures the production frontend to use `/api` through CloudFront.                       |

## AWS Deployment

Orbit uses `orbit-stack.yaml` as its unified CloudFormation template. Release artifacts are built locally, published to a private S3 artifact bucket under an immutable versioned prefix, and deployed through the AWS Management Console. Deployment does not require GitHub Actions, CodePipeline, CloudFormation Git sync, or a local CloudFormation deployment command.

### Prerequisites

- AWS Academy Learner Lab access and a current session.
- AWS Management Console access to CloudFormation, Lambda, S3, CloudFront, DynamoDB, and the existing Lambda execution role.
- An S3 artifact bucket in the deployment account/region. Keep Block Public Access enabled. The publishing identity needs `s3:ListBucket` and `s3:PutObject`; the Lambda execution role needs `s3:GetObject` for release artifacts.
- A Lambda execution role ARN in the deployment account, with CloudWatch Logs and DynamoDB data access. The stack grants that role access to its frontend bucket through a bucket policy. If the account denies DynamoDB table resource policies, set `TableResourcePolicyEnabled` to `false` and ensure the role has table access.
- Python 3.10 or newer, Node.js/npm, and AWS CLI v2 on the packaging/publishing computer.

AWS Academy credentials are temporary. For S3 publication, use the credentials exported by the Learner Lab or configure a short-lived AWS CLI profile. The publishing script uses the standard AWS CLI credential chain and never prints or stores credential values. The CloudFormation create/update itself can be performed in the console.

### Package a release

Choose a new release ID for every content change, such as a date plus short Git revision. Do not reuse a release ID.

```powershell
.\scripts\package-release.ps1 -ReleaseId 2026-11-04-a1b2c3d
```

The script runs `npm ci` and `npm run build` with a release-specific Vite asset base. It creates deterministic ZIPs and validates their contents before publication:

- `artifacts/releases/<release-id>/orbit-backend.zip` contains only `app.py` at the ZIP root. Boto3 is supplied by the Python 3.12 Lambda runtime.
- `artifacts/releases/<release-id>/orbit-frontend.zip` contains the built site with `index.html` at its root and forward-slash ZIP entry paths. Asset URLs point to `/releases/<release-id>/`.
- `artifacts/releases/<release-id>/orbit-stack.yaml` is the exact unified template for this release.
- `artifacts/releases/<release-id>/release.json` records artifact keys and SHA-256 digests.

The package command refuses to overwrite an existing local release directory. Generated release artifacts are ignored by Git and should not be committed.

### Publish artifacts to S3

Use AWS Academy's current temporary credentials (or pass a configured profile):

```powershell
.\scripts\publish-release.ps1 `
  -ReleaseId 2026-11-04-a1b2c3d `
  -ArtifactBucket YOUR_PRIVATE_ARTIFACT_BUCKET `
  -Region us-east-1
```

Optionally add `-Profile your-temporary-profile`. The script revalidates the release, checks that the S3 release prefix is unused, then uploads the template, both ZIPs, and manifest under `releases/<release-id>/`. A failed or partial upload leaves that prefix reserved; package and publish a new release ID for a clean retry. The script prints the CloudFormation template URL and the exact parameter values to use. It does not create or update a stack.

### Create the initial stack

1. In the AWS Console, open **CloudFormation → Create stack → With new resources (standard)**.
2. Choose the template URL printed by `publish-release.ps1`. The console identity must be able to read that object.
3. Enter a stack name, for example `orbit`.
4. Set parameters from the publishing output:
   - `ArtifactBucket`: the private artifact bucket name.
   - `BackendZipKey`: the printed `BackendZipKey`.
   - `FrontendZipKey`: the printed `FrontendZipKey`.
   - `ArtifactVersion`: the release ID.
   - `ExecutionRoleArn`: the existing Lambda execution role ARN in this account.
   - `TableResourcePolicyEnabled`: `true` if the account permits the table resource policy; otherwise `false` with equivalent identity permissions on the role.
5. Review the CloudFormation change set and submit. Wait for `CREATE_COMPLETE`; CloudFront distribution deployment can take additional time.
6. Open the stack's **Outputs** tab and use `WebsiteURL`.

The stack creates the private frontend bucket, CloudFront distribution and OACs, Lambda Function URL and API, DynamoDB table, and the custom resource that publishes the frontend. The DynamoDB table has `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain` to protect user data.

Ordinary Lambda and frontend releases do not replace the table. Its name is fixed from the stack name; a future key-schema or table-name change that requires replacement needs a planned migration to a distinct table name because retention intentionally preserves the current table. After deleting a stack, recreating it with the same name also requires importing/adopting the retained table or using a distinct table name and planning the data migration.

### Update an existing stack

1. Package and publish a new release with a new release ID.
2. Open the existing stack and choose **Update stack**.
3. Replace the template with the new release's printed template URL (the infrastructure changes are versioned with the release).
4. Keep the stack name and `ExecutionRoleArn` unchanged. Update `ArtifactBucket`, `BackendZipKey`, `FrontendZipKey`, and `ArtifactVersion` to the new release values.
5. Review the change set. Confirm that `OrbitFunction` is updated in place and that the frontend distribution and S3 bucket are not replaced. Submit and wait for `UPDATE_COMPLETE`.
6. Verify the new release using the same checks below.

The Lambda `Code.S3Key` parameter change triggers a code update while retaining the same Lambda logical resource and function name. A change to the custom resource's frontend key/version triggers content publication without changing the CloudFront distribution. Do not update a release in place or reuse its release ID.

### Verification

- Confirm CloudFormation reaches `CREATE_COMPLETE` or `UPDATE_COMPLETE`; inspect **Events** for failed resources.
- Open `WebsiteURL` from stack Outputs and check that the frontend loads.
- Request `<WebsiteURL>/api/health`; expect `{"status":"ok","service":"orbit"}`.
- Create/open a workspace, add a task, refresh, and verify it persists. Confirm project and calendar-import paths if those features are part of the release.
- Check CloudWatch logs for `OrbitFunction` and `FrontendDeployer` if requests or deployment resources fail.
- These checks are the operator's live AWS verification. Local packaging, tests, and CloudFormation validation do not prove AWS Academy permissions or live distribution behavior.

### Troubleshooting

- **S3 publication fails:** restart the Learner Lab and refresh temporary credentials. Confirm the CLI identity can list the artifact bucket and put objects. Do not pass long-term keys on the command line.
- **Release prefix already exists:** use a new release ID. Published prefixes are immutable; partial uploads are not overwritten.
- **Template cannot be loaded:** confirm the console identity can read the versioned template object and the URL is in the deployment region.
- **CloudFormation rejects the table policy:** set `TableResourcePolicyEnabled` to `false` and verify the Lambda role has DynamoDB permissions.
- **Frontend custom resource fails:** inspect its CloudWatch log stream and CloudFormation event reason. It validates the full ZIP before upload, writes versioned assets first, and changes root `index.html` last. Older release assets remain to support cached pages and stack rollback.
- **Frontend is stale:** confirm `ArtifactVersion` changed and `FrontendZipKey` points to the new release. Wait for CloudFront propagation; root HTML is published with no-cache headers and assets use immutable release paths.
- **Lambda code did not update:** ensure `BackendZipKey` changed to the new release path and inspect the change set before submission.
- **Custom resource cannot read/write objects:** grant the execution role read access to the artifact prefix and ensure the stack's frontend bucket policy was created. Its role also needs CloudWatch Logs permissions.

### Resource cleanup

Deleting the CloudFormation stack removes its generated frontend bucket contents, CloudFront distribution, Lambda functions, URL configuration, and related resources. The DynamoDB table is retained deliberately to protect user data. Because its name is derived from the stack name, a same-name stack recreation must import/adopt the retained table or use a distinct table name and plan a data migration. Export or back up anything needed before separately deleting that retained table through an explicit, reviewed data-retention process. Artifact bucket objects are not deleted by the stack; remove old release prefixes manually only after they are no longer needed for rollback or audit.

The older `template.yaml`, `orbit-frontend-template.yaml`, `deploy-orbit.ps1`, and `deploy-frontend.ps1` are retained for reference. Use only the unified `orbit-stack.yaml` release workflow above for new deployments and application updates.
## API Endpoints

The deployed API is accessed through the CloudFront `/api` prefix.

| Method | Endpoint             | Description                             |
| ------ | -------------------- | --------------------------------------- |
| GET    | `/api/health`        | Check backend health                    |
| POST   | `/api/spaces`        | Create a workspace                      |
| POST   | `/api/spaces/open`   | Open a workspace using an access code   |
| GET    | `/api/spaces/me`     | Retrieve the active workspace           |
| GET    | `/api/items`         | Retrieve responsibilities               |
| POST   | `/api/items`         | Create a responsibility                 |
| PATCH  | `/api/items/{id}`    | Update a responsibility                 |
| POST   | `/api/items/import`  | Import calendar events                  |
| GET    | `/api/projects`      | Retrieve accessible projects            |
| POST   | `/api/projects`      | Create a collaborative project          |
| POST   | `/api/projects/join` | Join a project using an invitation code |

Workspace-specific endpoints require the `x-orbit-access-code` header.

A newly created workspace receives a 24-character access code. The code should be saved because there is currently no account-recovery mechanism.

Due dates must be valid ISO 8601 timestamps containing timezone information.

## Security

Orbit incorporates several AWS infrastructure security controls.

### Implemented Controls

- **HTTPS:** CloudFront provides encrypted browser connections.
- **Private S3 Hosting:** Public bucket access is blocked.
- **Origin Access Control:** CloudFront uses signed requests to access S3 and the Lambda Function URL.
- **IAM-Protected Lambda URL:** The backend Function URL requires AWS IAM authentication.
- **Restricted Service Permissions:** The backend execution role requires permissions to access the DynamoDB table and write logs.
- **No Browser AWS Credentials:** AWS credentials are not embedded in the React frontend.
- **Workspace Access Codes:** Application data is scoped to workspaces identified by access codes.

### Security Limitations

Orbit is a course demonstration and should not be treated as a production-ready application.

- Workspace access codes function as bearer credentials rather than full user authentication.
- There is no Cognito-based identity management, account recovery, or rate limiting.
- Project invitation codes do not provide role-based membership controls.
- The public API permits workspace creation, so additional abuse protection would be necessary for production use.
- The application has not undergone a comprehensive production security assessment.

**Do not store sensitive student records, passwords, or other private information in the demonstration environment.**

## Current Limitations and Future Improvements

The current implementation prioritizes a functioning AWS architecture and a demonstrable serverless application.

Potential improvements include:

- Amazon Cognito authentication and user management
- Role-based project permissions
- API request throttling and additional security controls
- DynamoDB pagination and improved query access patterns
- Responsibility deletion and additional task-management features
- Automatic calendar synchronization through authorized integrations
- Reminders and notifications
- Automated infrastructure and application testing
- Additional CloudWatch monitoring and operational metrics
- Automated deployment pipelines

The current DynamoDB listing implementation paginates scans. A purpose-built indexed access pattern may be more efficient for substantially larger datasets.

Calendar imports are performed using downloaded `.ics` files. Automatic calendar account synchronization is not implemented.

## Project Team

**University:** University of Texas at Arlington
**Course:** CSE 4333 – Cloud Computing
**Project:** Orbit

**Team Members:**

- Robert Asumeng
- Emily Ford

## Project Summary

Orbit demonstrates the deployment of a functioning serverless web application using AWS-managed infrastructure.

The project integrates Amazon CloudFront, S3, Lambda, DynamoDB, IAM, CloudWatch, CloudFormation, and AWS SAM into a single cloud-based system.

Through the implementation of Orbit, the team gained practical experience with cloud architecture, infrastructure provisioning, service integration, IAM permissions, serverless computing, persistent storage, deployment automation, and troubleshooting within the constraints of an AWS Academy environment.

The final application can be accessed through a public HTTPS endpoint without requiring the user's computer to host the application.

**Repository:** [https://github.com/rasumeng/Orbit](https://github.com/rasumeng/Orbit)
