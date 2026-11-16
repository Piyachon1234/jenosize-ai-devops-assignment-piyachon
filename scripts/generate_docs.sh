#!/usr/bin/env bash
set -euo pipefail
mkdir -p data

cat << 'EOF' > data/01_vpn_access.md
#coporate VPN Access & wireguard setup
Employees connecting to internal staging or production VPCs  must use the Jenosize Wireguard VPN client. Request access via ServiceNow ticket approved. Profiles expire in 90 days
EOF

cat << 'EOF' > data/02_sso_mfa_reset.md
#SSO & Hardware MFA Token Reset
All internal tools use SSO with FIDO2 WebAuthn MFA. 
EOF

cat <<'EOF'> data/03_incident_response_sla.md
SEV-1 critical production outages require a 15-minute response SLA and <1 hour MTTR target. Page the on-call SRE via PagerDuty, open an #inc-YYYYMMDD Slack war room, and publish a blameless postmortem within 48 hours.
EOF

cat << 'EOF' > data/04_cicd_deployment_policy.md
# CI/CD Pipeline & Canary Deployment Policy
All repositories must pass Ruff linting, Pytest unit tests, and Trivy vulnerability scans before building container images. Production releases use Canary deployments (20% traffic shift for 10 minutes) with automatic rollback if HTTP 5xx exceeds 2%.
EOF

cat << 'EOF' > data/05_rag_knowledge_base_guide.md
# RAG Knowledge Base & pgvector Indexing
Jenie Helpdesk AI indexes markdown runbooks into PostgreSQL using the pgvector extension and cosine similarity search. Run POST /ingest or trigger the indexer worker whenever markdown documentation is updated.
EOF

cat << 'EOF' > data/06_cloud_finops_budget_alerts.md
# Cloud FinOps & AI Token Cost Optimization
Tag all AWS resources with Environment, Squad, and CostCenter. AI inference workloads use Redis semantic caching and CPU/GPU mixed autoscaling to reduce LLM token spend by up to 40%.
EOF

cat << 'EOF' > data/07_database_backup_dr.md
# Database Backups & Disaster Recovery Runbook
Production PostgreSQL databases run Multi-AZ with automated daily snapshots and Point-in-Time Recovery (PITR) to S3 (RPO < 5 minutes, RTO < 30 minutes). DR restore drills are executed quarterly.
EOF

cat << 'EOF' > data/08_kubernetes_pod_troubleshooting.md
# Kubernetes Pod Troubleshooting (CrashLoopBackOff & OOMKilled)
Inspect failing pods using kubectl describe pod and kubectl logs --previous. Ensure livenessProbe and readinessProbe target GET /healthz and memory limits leave a 25% headroom buffer.
EOF

cat << 'EOF' > data/09_secret_rotation_policy.md
# Secrets Management & Rotation Policy
Never commit plaintext secrets or .env files to Git. Production workloads retrieve credentials dynamically from AWS Secrets Manager encrypted with customer-managed KMS keys and rotated every 30 days.
EOF

cat << 'EOF' > data/10_ai_token_rate_limits.md
# API Rate Limiting & WAF Protection
Public AI endpoints enforce a sliding-window rate limit of 60 requests per minute per IP via Redis and AWS WAFv2 rate-based rules to prevent Denial-of-Wallet (DoW) and prompt flooding attacks.
EOF