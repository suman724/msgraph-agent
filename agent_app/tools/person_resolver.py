from typing import Optional, Dict

def resolve_person(name: str) -> Dict[str, Optional[str]]:
    """
    Resolves a person's name to their email address.
    """
    # Mock implementation
    # In production this would query a directory service or use previous context.
    mock_directory = {
        "john johnson": "john.johnson@example.com",
        "derek": "derek.w@example.com"
    }
    
    email = mock_directory.get(name.lower())
    return {
        "name": name,
        "email": email,
        "confidence": 1.0 if email else 0.0
    }
