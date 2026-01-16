from src.agents.validation_agent import ValidationAgent
from datetime import datetime
import json

MAX_REFINEMENT_ITER = 3
CONFIDENCE_THRESHOLD = 0.85

def refine_artifact(artifact):
    """
    Sends feedback to Elicitation Agent or stakeholder.
    Placeholder: Here we simulate refinement by appending clarifications.
    """
    # Example refinement: add missing "when"
    if any(issue["type"] == "missing_condition" and issue["dimension"] == "when" for issue in artifact["validation"]["issues"]):
        artifact["text"] += " The action must happen within 1 business day."
    return artifact

def process_artifacts(artifacts):
    validation_agent = ValidationAgent()
    project_report = {
        "total_issues": {},
        "average_confidence": 0.0,
        "critical_issues": []
    }

    total_confidence = 0

    for artifact in artifacts:
        iteration = 0
        while iteration < MAX_REFINEMENT_ITER:
            artifact["validation"] = validation_agent.validate_requirement(
                artifact["text"],
                context=artifact.get("constraints")
            )

            confidence = artifact["validation"]["confidence_score"]
            total_confidence += confidence

            # Update project-level issue count
            for issue in artifact["validation"]["issues"]:
                issue_type = issue["type"]
                project_report["total_issues"].setdefault(issue_type, 0)
                project_report["total_issues"][issue_type] += 1

                # Collect critical issues
                if issue["severity"] == "high":
                    project_report["critical_issues"].append({
                        "artifact_id": artifact["artifact_id"],
                        "issue": issue
                    })

            if confidence >= CONFIDENCE_THRESHOLD:
                break  # No refinement needed
            else:
                artifact = refine_artifact(artifact)
                iteration += 1

    # Final project-level report
    project_report["average_confidence"] = total_confidence / len(artifacts)
    return artifacts, project_report

# Example usage
if __name__ == "__main__":
    artifacts = [
        {
            "artifact_id": "REQ_001",
            "text": "The system shall be fast and user-friendly",
            "constraints": {
                "withdrawal": lambda v: v["withdrawal"] <= 500
            }
        },
        {
            "artifact_id": "REQ_002",
            "text": "User must login, no authentication required"
        }
    ]

    validated_artifacts, project_report = process_artifacts(artifacts)

    print("=== VALIDATED ARTIFACTS ===")
    print(json.dumps(validated_artifacts, indent=4))
    print("\n=== PROJECT REPORT ===")
    print(json.dumps(project_report, indent=4))
