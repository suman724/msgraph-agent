from typing import List, Dict, Any

def extract_action_items(text: str) -> List[Dict[str, Any]]:
    """
    Extracts action items from a given text.
    """
    # Mock implementation
    # Real implementation would use an LLM or regex to find action items.
    
    action_items = []
    lines = text.split('\n')
    for line in lines:
        if "action:" in line.lower() or "todo:" in line.lower():
            action_items.append({
                "text": line.strip(),
                "status": "open"
            })
            
    return action_items
