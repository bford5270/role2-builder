# Infrastructure helpers

Files here aren't deployed automatically — they're copy-pasteable building blocks for the AWS migration. Apply them with the AWS CLI / console / your IaC of choice.

## What's here

```
infra/
├── README.md                          (this file)
└── iam/
    ├── bedrock-invoke-policy.json     The minimum to call Claude on Bedrock.
    ├── bedrock-readonly-policy.json   Optional: list-models for diagnostic tooling.
    ├── apprunner-trust-policy.json    Trust relationship for an App Runner instance role.
    └── ecs-task-trust-policy.json     Trust relationship for an ECS Fargate task role.
```

## How to use these IAM files

The policies have **placeholders** (`REGION`, `ACCOUNT_ID`, model ids) — replace them before applying.

### 1. Local dev / Railway service: IAM user with access keys

Easiest path for non-AWS-native deployments. Works for Railway and your laptop.

```bash
# 1. Edit infra/iam/bedrock-invoke-policy.json — replace REGION + ACCOUNT_ID +
#    the model id with whatever you got from the Bedrock console.

# 2. Create the user + policy + key.
aws iam create-user --user-name role2-builder-runtime
aws iam put-user-policy \
  --user-name role2-builder-runtime \
  --policy-name BedrockInvoke \
  --policy-document file://infra/iam/bedrock-invoke-policy.json
aws iam create-access-key --user-name role2-builder-runtime
# Save AccessKeyId + SecretAccessKey somewhere safe (e.g., Railway env vars).
```

### 2. AWS App Runner: instance role

App Runner uses an instance role (no access keys in env vars).

```bash
aws iam create-role \
  --role-name role2-builder-apprunner-instance \
  --assume-role-policy-document file://infra/iam/apprunner-trust-policy.json

aws iam put-role-policy \
  --role-name role2-builder-apprunner-instance \
  --policy-name BedrockInvoke \
  --policy-document file://infra/iam/bedrock-invoke-policy.json

# Then in App Runner service config, set "Instance role" to the role arn above.
```

### 3. ECS Fargate: task role

```bash
aws iam create-role \
  --role-name role2-builder-ecs-task \
  --assume-role-policy-document file://infra/iam/ecs-task-trust-policy.json

aws iam put-role-policy \
  --role-name role2-builder-ecs-task \
  --policy-name BedrockInvoke \
  --policy-document file://infra/iam/bedrock-invoke-policy.json

# Then in your ECS task definition, set "taskRoleArn" to this role's arn.
```

## Verifying the IAM grant works

After applying, run the doctor against your local machine with the credentials configured:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0
export CASE_PROVIDER=bedrock
python -m backend.scripts.doctor
```

The doctor's "Converse smoke test" line will pass when the IAM grant + model id + region all line up. If it fails with `AccessDeniedException`, the IAM policy didn't match the resource arn the SDK is calling. If it fails with `ValidationException`, the model id is wrong for the region or model access wasn't granted in the Bedrock console.

## What's NOT here yet

- CloudFormation / Terraform templates for full unified deployment (App Runner + RDS + Amplify). Premature — wait until a region / account is chosen.
- Bedrock VPC endpoint config. Only needed if the runtime can't reach the public internet (relevant in GovCloud, not in the current Railway/Vercel setup).
- Secrets Manager wiring. Use Railway env vars or AWS Secrets Manager + the AWS SDK; both work.
