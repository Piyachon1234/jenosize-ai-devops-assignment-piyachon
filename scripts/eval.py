import os
import sys
import requests

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
LATENCY_SLO_MS = 1000

TEST_CASES = [
    {"query": "How do I connect to the corporate WireGuard VPN?", "expected_source": "01_vpn_access"},
    {"query": "What is the response SLA and MTTR target for a SEV-1 incident?", "expected_source": "03_incident_response_sla"},
    {"query": "How does Canary deployment automatic rollback work in CI/CD?", "expected_source": "04_cicd_deployment_policy"},
    {"query": "What are the RPO and RTO targets for PostgreSQL disaster recovery?", "expected_source": "07_database_backup_dr"},
    {"query": "How are secrets managed and rotated in production?", "expected_source": "09_secret_rotation_policy"},
]

def main():
    print(f"Running Jenie AI helpdesk")
    passed = 0
    latencies = []
    
    for idx, tc in enumerate(TEST_CASES, 1):
        resp = response.post(f"{API_BASE}/ask", json={"query": tc["query"]}, timeout=10)
        resp.raise_for_status()
        body = resp.json()

        sources = [s["title"] for s in body.get("sources", [])]
        top_score = body["scores"][0][score] if body.get("sources") else 0.0
        latency_ms = body.get("latency_ms", 9999)
        latencies.append(latency_ms)

        hit = tc["expected_score"] in sources
        slo_ok = latency_ms <= LATENCY_SLO_MS
        status = "PASS" if (hit and slo_ok) else "FAIL"
        if status == "PASS":
            passed +=1

        print(
            f"[{status}] Q{idx}: '{tc['query']}'\n"
            f"       Expected: {tc['expected_source']} | Retrieved: {sources} (top_score={top_score}) | Latency: {latency_ms}ms"
        )
        precision_at_3 = passed / len(TEST_CASES)
        avg_latency = sum(latencies) / len(latencies)
        print(f"Summary: {passed}/{len(TEST_CASES)} Passed | Precision@3: {precision_at_3:.0%} | Avg Latency: {avg_latency:.1f}ms")
        if passed < 4:
            sys.exit(1)

if __name__ =="__main__":
    main()