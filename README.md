# Orbit

**A Serverless Student Life Management Dashboard Built on AWS**

Orbit is a cloud-based student responsibility management application developed for **CSE 4333 – Cloud Computing** at the University of Texas at Arlington.

The project addresses the challenge of managing responsibilities across academics, employment, leadership, personal commitments, and collaborative projects through a centralized dashboard.

Beyond its application features, Orbit demonstrates the design, deployment, integration, and management of cloud infrastructure using Amazon Web Services (AWS).

The application is deployed entirely on AWS using a serverless architecture. Users access Orbit through Amazon CloudFront, while AWS Lambda handles backend operations and Amazon DynamoDB provides persistent storage.

**Live Application:** [https://d10op2gg45n9aa.cloudfront.net](https://d10op2gg45n9aa.cloudfront.net)

*Note: The application URL is associated with an specific instance of AWS Academy sandbox deployment and may change if the infrastructure is recreated.*

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
│   ├── deploy-orbit.ps1
│   ├── deploy-frontend.ps1
│   └── teardown-orbit.ps1
├── docs/
│   └── MIDPOINT_EVALUATION.md
├── template.yaml
├── orbit-frontend-template.yaml
└── README.md
```

### Infrastructure Files

| File                           | Purpose                                                                                    |
| ------------------------------ | ------------------------------------------------------------------------------------------ |
| `template.yaml`                | Defines the Lambda backend, DynamoDB table, and Function URL.                              |
| `orbit-frontend-template.yaml` | Defines S3 hosting, CloudFront, Origin Access Controls, and Lambda invocation permissions. |
| `scripts/deploy-orbit.ps1`     | Validates, builds, and deploys the backend infrastructure.                                 |
| `scripts/deploy-frontend.ps1`  | Builds React, uploads assets to S3, and invalidates CloudFront.                            |
| `scripts/teardown-orbit.ps1`   | Provides an opt-in deletion workflow for the backend CloudFormation stack.                 |
| `frontend/.env.production`     | Configures the production frontend to use `/api` through CloudFront.                       |

## AWS Deployment

Orbit can be deployed to an AWS Academy Learner Lab environment using a unified AWS CloudFormation template.

The deployment provisions the frontend, backend, database, and networking infrastructure as a single CloudFormation stack. Once the application artifacts are prepared in Amazon S3, deployment can be completed through the AWS Management Console without configuring a local AWS CLI profile.

### Prerequisites

- Access to an AWS Academy Learner Lab
- An existing `lambda-run-role` with the necessary S3, DynamoDB, and CloudWatch permissions
- A private S3 bucket containing the application deployment artifacts
- The unified infrastructure template (`orbit-stack.yaml`)

For preparing new application releases, Node.js, Python, and Git are also required.

### 1. Start the AWS Academy Environment

1. Sign in to AWS Academy.
2. Start the Learner Lab.
3. Open the AWS Management Console.
4. Select **US East (N. Virginia) — `us-east-1`**.
5. Confirm that the existing `lambda-run-role` is available through IAM.

AWS Academy accounts use temporary credentials and may have restricted IAM permissions.

### 2. Prepare the Application Artifacts

Orbit requires three deployment files:

| File | Purpose |
|---|---|
| `orbit-stack.yaml` | Unified CloudFormation infrastructure template |
| `orbit-backend.zip` | Python Lambda backend package |
| `orbit-frontend.zip` | Compiled React frontend package |

The backend ZIP must contain `app.py` at its root.

The frontend must first be compiled using:

```powershell
cd frontend
npm ci
npm run build
cd ..
```

Create the frontend ZIP using Python to preserve forward-slash paths:

```powershell
@'
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path("frontend/dist")
output = Path("artifacts/orbit-frontend.zip")
output.parent.mkdir(exist_ok=True)

with ZipFile(output, "w", ZIP_DEFLATED) as archive:
    for file in root.rglob("*"):
        if file.is_file():
            archive.write(file, file.relative_to(root).as_posix())
'@ | python -
```

For a backend containing only the current Lambda handler, package `backend/app.py` at the ZIP root. Additional dependencies must be included if introduced later.

### 3. Upload Artifacts to S3

In the AWS Console:

1. Navigate to **Amazon S3**.
2. Create or open a private artifact bucket.
3. Keep Block Public Access enabled.
4. Enable bucket versioning.
5. Upload the three deployment files.

Our tested deployment uses:

`orbit-deployment-artifacts-1002095331`

The artifact bucket must be accessible in the AWS account used for deployment. A separate AWS Academy account may require its own artifact bucket and uploads.

### 4. Deploy with CloudFormation

1. Navigate to **AWS CloudFormation → Create stack**.
2. Select **With new resources (standard)**.
3. Provide the S3 URL of `orbit-stack.yaml`, or upload the template file directly.
4. Choose a stack name, such as `orbit-unified`.
5. Configure the deployment parameters.

| Parameter | Example value |
|---|---|
| `ArtifactBucket` | `orbit-deployment-artifacts-1002095331` |
| `ArtifactVersion` | `v1` |
| `BackendZipKey` | `orbit-backend.zip` |
| `FrontendZipKey` | `orbit-frontend.zip` |
| `ExecutionRoleArn` | ARN of the existing `lambda-run-role` |
| `TableResourcePolicyEnabled` | `true` |

The execution role ARN must belong to the current AWS account.

6. Review the stack options and deployment parameters.
7. Submit the CloudFormation stack.
8. Monitor the **Events** tab until the stack reaches `CREATE_COMPLETE`.

CloudFormation automatically creates the DynamoDB table, Lambda functions, IAM-protected Function URL, private S3 frontend bucket, CloudFront distribution, and origin-access permissions. A Lambda-backed custom resource uploads the frontend assets to the hosting bucket.

### 5. Access Orbit

After the deployment completes:

1. Open **CloudFormation → Stacks → orbit-unified**.
2. Select the **Outputs** tab.
3. Locate `WebsiteURL`.
4. Open the generated HTTPS URL.

For the successfully tested unified deployment, the URL is:

https://d2dov77uex6fah.cloudfront.net

This URL belongs to the current sandbox deployment and may change when the infrastructure is recreated.

### 6. Verify the Deployment

Test the backend by navigating to:

`https://YOUR_CLOUDFRONT_DOMAIN/api/health`

Expected response:

```json
{
  "status": "ok",
  "service": "orbit"
}
```

Then test application persistence:

1. Create a workspace.
2. Create a responsibility.
3. Refresh the application.
4. Confirm the responsibility remains available.
5. Mark it completed and refresh again.
6. Confirm that the completed status persists.

These tests verify communication among CloudFront, Lambda, and DynamoDB.

### 7. Updating an Existing Deployment

To deploy updated application code:

1. Rebuild the changed application packages.
2. Upload the new ZIP files to S3.
3. Open the existing CloudFormation stack.
4. Select **Update stack**.
5. Use the existing infrastructure template, or upload a revised template if infrastructure has changed.
6. Change `ArtifactVersion` to a new value, such as `v2`.
7. Review and submit the update.

For reproducible releases, store artifacts under version-specific S3 keys rather than overwriting previously published packages.

The `ArtifactVersion` parameter triggers a redeployment of the frontend custom resource. Backend code changes should also use a new S3 object key or object version so CloudFormation recognizes the update.

### AWS Academy Considerations

The deployment was tested successfully in AWS Academy using CloudFormation, Lambda, S3, DynamoDB, CloudFront, and IAM.

CloudFormation Git sync and GitHub-based CodePipeline integration were unavailable because of AWS Organizations service control policy restrictions.

As a result, Orbit uses **CloudFormation-based deployment with S3-hosted application artifacts**, avoiding those restricted integrations.

The current workflow automates infrastructure provisioning and application deployment after the artifacts have been prepared. Artifact packaging and publication remain separate steps.

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

The current DynamoDB listing implementation uses scans with fixed limits and does not provide full pagination.

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
