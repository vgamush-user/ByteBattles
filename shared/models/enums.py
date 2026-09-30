from enum import Enum

class UserType(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"

class Difficulty(str, Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"

class Verdict(str, Enum):
    PENDING = "PD"
    ACCEPTED = "AC"
    WRONG_ANSWER = "WA"
    TIME_LIMIT_EXCEEDED = "TLE"
    MEMORY_LIMIT_EXCEEDED = "MLE"
    COMPILATION_ERROR = "CE"
    RUNTIME_ERROR = "RE"
    SKIPPED = "SKP"

class Language(str, Enum):
    C = "C"
    CPP = "CPP"
    PYTHON = "PY"
    JAVA = "JAVA"

