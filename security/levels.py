from enum import Enum


class SecurityLevel(str, Enum):
    SAFE = "SAFE"
    MODERATE = "MODERATE"
    CRITICAL = "CRITICAL"
