# src/integration/validate_artifacts.py

import json
from src.agents.validation_agent import ValidationAgent


ARTIFACTS = [
    # ----------------- GOOD REQUIREMENTS -----------------
    {"artifact_id": "REQ_001", "text": "The system shall allow users to login using email and password."},
    {"artifact_id": "REQ_002", "text": "The application shall save user preferences securely."},
    {"artifact_id": "REQ_003", "text": "The system shall send a confirmation email after registration."},
    {"artifact_id": "REQ_004", "text": "Users shall be able to reset their password using the registered email."},
    {"artifact_id": "REQ_005", "text": "The system shall log all user actions for auditing purposes."},
    {"artifact_id": "REQ_006", "text": "The API shall respond to GET requests within 2 seconds."},
    {"artifact_id": "REQ_007", "text": "The system shall allow administrators to deactivate inactive accounts."},
    {"artifact_id": "REQ_008", "text": "User sessions shall expire after 30 minutes of inactivity."},
    {"artifact_id": "REQ_009", "text": "The system shall encrypt sensitive user data using AES-256."},
    {"artifact_id": "REQ_010", "text": "Reports shall be downloadable in PDF format."},

    # ------------- SLIGHTLY PROBLEMATIC -----------------
    {"artifact_id": "REQ_011", "text": "The system shall be fast and user-friendly."},
    {"artifact_id": "REQ_012", "text": "The application shall provide feedback when possible."},
    {"artifact_id": "REQ_013", "text": "The system shall send notifications as appropriate."},
    {"artifact_id": "REQ_014", "text": "Users should be able to export their data if necessary."},
    {"artifact_id": "REQ_015", "text": "The system shall allow login using a username or email."},
    {"artifact_id": "REQ_016", "text": "The API should respond efficiently under load."},
    {"artifact_id": "REQ_017", "text": "The system shall provide help information when requested."},
    {"artifact_id": "REQ_018", "text": "The application should maintain a secure environment."},
    {"artifact_id": "REQ_019", "text": "Reports shall be generated in a timely manner."},
    {"artifact_id": "REQ_020", "text": "The system should consider data privacy."},

    # ------------- CRITICALLY PROBLEMATIC -----------------
    {"artifact_id": "REQ_021", "text": "User must login, no authentication required."},
    {"artifact_id": "REQ_022", "text": "Users can withdraw any amount, but max daily withdrawal is $500."},
    {"artifact_id": "REQ_023", "text": "Payment shall be optional, but required for premium features."},
    {"artifact_id": "REQ_024", "text": "The system shall allow data deletion, but retain all user data indefinitely."},
    {"artifact_id": "REQ_025", "text": "Email notifications shall be sent immediately, except during business hours."},
    {"artifact_id": "REQ_026", "text": "The system must encrypt data, but store passwords in plain text."},
    {"artifact_id": "REQ_027", "text": "Administrator cannot deactivate accounts, but can block login."},
    {"artifact_id": "REQ_028", "text": "Response time shall be <1s, but processing may take up to 5s."},
    {"artifact_id": "REQ_029", "text": "User can access admin panel, unless they are admin."},
    {"artifact_id": "REQ_030", "text": "The system shall allow guest checkout, but require login for all purchases."},
]



def generate_project_report(validated_artifacts: list) -> dict:
    total_confidence = 0.0
    total_requirements = len(validated_artifacts)

    issue_counter = {}
    critical_issues = []

    for artifact in validated_artifacts:
        validation = artifact["validation"]
        total_confidence += validation["confidence_score"]

        for issue in validation["issues"]:
            issue_type = issue["type"]
            issue_counter[issue_type] = issue_counter.get(issue_type, 0) + 1

            if issue.get("severity") == "high":
                critical_issues.append({
                    "artifact_id": artifact["artifact_id"],
                    "issue": issue
                })

    return {
        "average_confidence": round(total_confidence / total_requirements, 2),
        "total_issues": issue_counter,
        "critical_issues": critical_issues
    }


if __name__ == "__main__":
    agent = ValidationAgent()
    validated = []

    for artifact in ARTIFACTS:
        validated.append(agent.validate_requirement(artifact))

    print("\n=== VALIDATED ARTIFACTS ===")
    print(json.dumps(validated, indent=4))

    print("\n=== PROJECT REPORT ===")
    print(json.dumps(generate_project_report(validated), indent=4))
