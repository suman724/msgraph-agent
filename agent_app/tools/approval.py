from typing import Dict, Any

def approval_gate(action_summary: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Requests user approval for a specific action.
    """
    print(f"\n[APPROVAL REQUEST] {action_summary}")
    print(f"Payload: {payload}")
    # For CLI interactive mode, we could ask for input. 
    # For this implementation, we will mock it or handle it in the main loop.
    return {
        "status": "pending",
        "message": "Approval requested"
    }
