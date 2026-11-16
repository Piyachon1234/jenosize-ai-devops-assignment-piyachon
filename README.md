# Security Baseline & Threat Model — Jenie Helpdesk AI

## 1. Threat Assumptions (STRIDE & OWASP Top 10 for LLM Applications)
1. **Denial of Wallet (DoW) & API Flooding (Availability / FinOps):**
   - *Threat:* Unauthenticated or malicious actors flood `POST /ask` with expensive queries to exhaust LLM token budgets or saturate vector search CPU.
   - *Mitigation:* Redis-backed sliding-window rate limiting (`RATE_LIMIT_PER_MIN=60` per IP) at the application layer, coupled with AWS WAFv2 rate-based rules at the ALB edge and Prometheus `JenieTokenCostAnomaly` alerting.
2. **Prompt Injection & Untrusted Context Retrieval (Integrity):**
   - *Threat:* Malicious instructions embedded in user queries or poisoned markdown files attempt to override system prompts or exfiltrate internal configuration.
   - *Mitigation:* Input length validation (`min_length=2, max_length=500` via Pydantic), read-only mounting of `/data` inside the API container (`/data:ro`), and strict separation between user query parameters and system prompt templates.
3. **Credential Leakage & Supply Chain Vulnerabilities (Confidentiality):**
   - *Threat:* Hardcoded database passwords/API keys in Git or vulnerable Python/OS packages in Docker images.
   - *Mitigation:* Zero secrets committed to Git (`.env.example` only); production secrets injected dynamically from KMS-encrypted **AWS Secrets Manager**. GitHub Actions runs **Trivy** (`vuln,secret,misconfig`) on both the repository filesystem and built container images, failing the pipeline on `HIGH` or `CRITICAL` findings.
4. **Lateral Movement & Container Escape (Privilege Escalation):**
   - *Threat:* Compromise of the web API container leading to host access or unauthorized AWS API calls.
   - *Mitigation:* Containers run as non-root UIDs (`10001` for API, `10002` for Worker), Kubernetes `automountServiceAccountToken: false`, `RuntimeDefault` seccomp profile, and network security groups restricting PostgreSQL (`5432`) strictly to the API/Worker security group.

## 2. Secrets Management Strategy
- **Local Development:** Uses `.env` (git-ignored) derived from `.env.example`.
- **Cloud Production (AWS):** Managed via **AWS Secrets Manager** (`jenie/prod/app-secrets`) encrypted with a dedicated customer-managed **AWS KMS Key** (`enable_key_rotation = true`). Secrets are injected into ECS Tasks / EKS Pods via `secretRef` at runtime and never written to disk.

## 3. Minimal Permissions / IAM & RBAC Approach
- **AWS IAM Split:** Separate `ecs_execution_role` (allowed only to pull ECR images and decrypt `jenie/${env}/app-secrets`) and `ecs_task_role` (scoped strictly to application runtime needs).
- **Network Segmentation:** RDS PostgreSQL (`pgvector`) resides in isolated private subnets (`10.20.16.0/20`, `10.20.32.0/20`) with no public IP route.

## 4. Basic WAF Architecture (AWS WAFv2 in Front of ALB)
In production, an **AWS WAFv2 WebACL** is attached to the Application Load Balancer with four layered rule groups:
1. `AWSManagedRulesCommonRuleSet` (blocks generic web exploits, LFI/RFI, XSS).
2. `AWSManagedRulesSQLiRuleSet` (protects PostgreSQL metadata queries).
3. `AWSManagedRulesAmazonIpReputationList` & Bot Control.
4. **Custom Rate-Based Rule:** Blocks source IPs exceeding 300 requests per 5-minute window to `/ask` or `/ingest`.