"""
Skill Security Guard & Constraints Validator

Regex-based static analysis of skill content with trust-level policies.
Inspired by Hermes Agent's skills_guard.py.
"""

import re
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, List, Tuple

logger = logging.getLogger(__name__)


class ThreatLevel(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"


class ThreatCategory(str, Enum):
    DATA_EXFILTRATION = "data_exfiltration"
    PROMPT_INJECTION = "prompt_injection"
    DESTRUCTIVE_OPS = "destructive_ops"
    REVERSE_SHELL = "reverse_shell"
    OBFUSCATION = "obfuscation"
    SUPPLY_CHAIN = "supply_chain"
    CREDENTIAL_EXPOSURE = "credential_exposure"
    INVISIBLE_UNICODE = "invisible_unicode"
    PERSISTENCE = "persistence"
    PRIVILEGE_ESCALATION = "privilege_escalation"


@dataclass
class Finding:
    category: ThreatCategory
    level: ThreatLevel
    pattern: str
    match: str
    line_number: int
    description: str


@dataclass
class ScanResult:
    findings: List[Finding] = field(default_factory=list)
    max_threat_level: ThreatLevel = ThreatLevel.SAFE
    passed: bool = True
    summary: str = ""


@dataclass
class ConstraintViolation:
    constraint: str
    message: str
    value: Any = None
    limit: Any = None


@dataclass
class ValidationResult:
    violations: List[ConstraintViolation] = field(default_factory=list)
    passed: bool = True


# ---------------------------------------------------------------------------
# Trust-level policies: which threat levels are allowed per source
# ---------------------------------------------------------------------------
TRUST_POLICIES = {
    "builtin": {ThreatLevel.SAFE, ThreatLevel.CAUTION, ThreatLevel.DANGEROUS},
    "agent-created": {ThreatLevel.SAFE, ThreatLevel.CAUTION},
    "community": {ThreatLevel.SAFE},
}

# ---------------------------------------------------------------------------
# Threat patterns: (regex, category, level, description)
# ---------------------------------------------------------------------------
_PATTERNS: List[Tuple[str, ThreatCategory, ThreatLevel, str]] = [
    # === DATA EXFILTRATION ===
    (r'curl\s+.*\|\s*(?:bash|sh|zsh)', ThreatCategory.DATA_EXFILTRATION, ThreatLevel.DANGEROUS,
     "curl piped to shell"),
    (r'wget\s+-O\s*-\s*.*\|', ThreatCategory.DATA_EXFILTRATION, ThreatLevel.DANGEROUS,
     "wget piped to command"),
    (r'nc\s+-[el]', ThreatCategory.DATA_EXFILTRATION, ThreatLevel.DANGEROUS,
     "netcat listener"),
    (r'ngrok\s+', ThreatCategory.DATA_EXFILTRATION, ThreatLevel.DANGEROUS,
     "ngrok tunneling"),
    (r'(?:cat|less|head)\s+~/\.(?:ssh|aws|gnupg|config)', ThreatCategory.DATA_EXFILTRATION, ThreatLevel.DANGEROUS,
     "reading sensitive dotfiles"),
    (r'requests\.post\(.*(?:api_key|token|secret|password)', ThreatCategory.DATA_EXFILTRATION, ThreatLevel.DANGEROUS,
     "HTTP POST with credentials"),
    (r'fetch\(.*method.*POST.*(?:key|token|secret)', ThreatCategory.DATA_EXFILTRATION, ThreatLevel.DANGEROUS,
     "fetch POST with credentials"),

    # === PROMPT INJECTION ===
    (r'ignore\s+(?:all\s+)?previous\s+instructions', ThreatCategory.PROMPT_INJECTION, ThreatLevel.DANGEROUS,
     "prompt injection: ignore previous instructions"),
    (r'disregard\s+(?:all\s+)?(?:prior|above|previous)\s+instructions', ThreatCategory.PROMPT_INJECTION, ThreatLevel.DANGEROUS,
     "prompt injection: disregard instructions"),
    (r'you\s+are\s+now\s+(?:a|an)\s+', ThreatCategory.PROMPT_INJECTION, ThreatLevel.CAUTION,
     "prompt injection: role reassignment"),
    (r'<\|endoftext\|>', ThreatCategory.PROMPT_INJECTION, ThreatLevel.DANGEROUS,
     "special token injection"),
    (r'system\s*prompt\s*:', ThreatCategory.PROMPT_INJECTION, ThreatLevel.CAUTION,
     "system prompt reference"),
    (r'jailbreak', ThreatCategory.PROMPT_INJECTION, ThreatLevel.DANGEROUS,
     "jailbreak keyword"),

    # === DESTRUCTIVE OPS ===
    (r'rm\s+-rf\s+/', ThreatCategory.DESTRUCTIVE_OPS, ThreatLevel.DANGEROUS,
     "recursive delete from root"),
    (r'rm\s+-rf\s+~', ThreatCategory.DESTRUCTIVE_OPS, ThreatLevel.DANGEROUS,
     "recursive delete home directory"),
    (r'mkfs\.', ThreatCategory.DESTRUCTIVE_OPS, ThreatLevel.DANGEROUS,
     "filesystem format"),
    (r'dd\s+if=.*of=/dev/', ThreatCategory.DESTRUCTIVE_OPS, ThreatLevel.DANGEROUS,
     "dd writing to device"),
    (r'DROP\s+(?:TABLE|DATABASE)', ThreatCategory.DESTRUCTIVE_OPS, ThreatLevel.DANGEROUS,
     "SQL DROP statement"),
    (r'DELETE\s+FROM\s+\w+\s*;', ThreatCategory.DESTRUCTIVE_OPS, ThreatLevel.CAUTION,
     "SQL DELETE without WHERE"),
    (r'shutil\.rmtree\s*\(\s*["\']/', ThreatCategory.DESTRUCTIVE_OPS, ThreatLevel.DANGEROUS,
     "Python rmtree from root"),
    (r'format\s+[A-Z]:', ThreatCategory.DESTRUCTIVE_OPS, ThreatLevel.DANGEROUS,
     "Windows drive format"),

    # === REVERSE SHELL ===
    (r'bash\s+-i\s+>&?\s*/dev/tcp/', ThreatCategory.REVERSE_SHELL, ThreatLevel.DANGEROUS,
     "bash reverse shell via /dev/tcp"),
    (r'/dev/tcp/\d', ThreatCategory.REVERSE_SHELL, ThreatLevel.DANGEROUS,
     "TCP device file access"),
    (r'nc\s+.*-e\s+/bin/', ThreatCategory.REVERSE_SHELL, ThreatLevel.DANGEROUS,
     "netcat reverse shell"),
    (r'python.*socket.*connect\s*\(', ThreatCategory.REVERSE_SHELL, ThreatLevel.DANGEROUS,
     "Python socket connect (potential reverse shell)"),
    (r'socat\s+.*EXEC:', ThreatCategory.REVERSE_SHELL, ThreatLevel.DANGEROUS,
     "socat exec shell"),
    (r'mknod\s+.*p\s*;', ThreatCategory.REVERSE_SHELL, ThreatLevel.DANGEROUS,
     "named pipe for reverse shell"),

    # === OBFUSCATION ===
    (r'base64\s+(?:--)?decode\s*\|', ThreatCategory.OBFUSCATION, ThreatLevel.DANGEROUS,
     "base64 decode piped to command"),
    (r'eval\s*\(', ThreatCategory.OBFUSCATION, ThreatLevel.CAUTION,
     "eval() call"),
    (r'exec\s*\(\s*compile', ThreatCategory.OBFUSCATION, ThreatLevel.DANGEROUS,
     "exec(compile(...))"),
    (r'chr\s*\(\s*\d+\s*\)\s*\+\s*chr', ThreatCategory.OBFUSCATION, ThreatLevel.CAUTION,
     "character-by-character string building"),
    (r'\\x[0-9a-fA-F]{2}.*\\x[0-9a-fA-F]{2}.*\\x[0-9a-fA-F]{2}', ThreatCategory.OBFUSCATION, ThreatLevel.CAUTION,
     "hex-encoded string sequence"),
    (r'atob\s*\(', ThreatCategory.OBFUSCATION, ThreatLevel.CAUTION,
     "JavaScript base64 decode"),

    # === SUPPLY CHAIN ===
    (r'pip\s+install\s+--index-url', ThreatCategory.SUPPLY_CHAIN, ThreatLevel.DANGEROUS,
     "custom pip index URL"),
    (r'npm\s+config\s+set\s+registry', ThreatCategory.SUPPLY_CHAIN, ThreatLevel.DANGEROUS,
     "custom npm registry"),
    (r'curl\s+.*\|\s*(?:sudo\s+)?(?:bash|sh)', ThreatCategory.SUPPLY_CHAIN, ThreatLevel.DANGEROUS,
     "curl piped to shell (supply chain)"),
    (r'wget\s+.*\|\s*(?:sudo\s+)?(?:bash|sh)', ThreatCategory.SUPPLY_CHAIN, ThreatLevel.DANGEROUS,
     "wget piped to shell"),
    (r'pip\s+install\s+(?!-r\s)(?!--upgrade\s)(?!\.\s)\S+\s*$', ThreatCategory.SUPPLY_CHAIN, ThreatLevel.CAUTION,
     "unpinned pip install"),

    # === CREDENTIAL EXPOSURE ===
    (r'(?:AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID)\s*=\s*["\']?\w{16,}', ThreatCategory.CREDENTIAL_EXPOSURE, ThreatLevel.DANGEROUS,
     "AWS credential in skill"),
    (r'(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|DEEPSEEK_API_KEY)\s*=', ThreatCategory.CREDENTIAL_EXPOSURE, ThreatLevel.DANGEROUS,
     "API key assignment"),
    (r'password\s*=\s*["\'][^"\']{4,}["\']', ThreatCategory.CREDENTIAL_EXPOSURE, ThreatLevel.CAUTION,
     "hardcoded password"),
    (r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----', ThreatCategory.CREDENTIAL_EXPOSURE, ThreatLevel.DANGEROUS,
     "private key embedded"),
    (r'sk-[a-zA-Z0-9]{20,}', ThreatCategory.CREDENTIAL_EXPOSURE, ThreatLevel.DANGEROUS,
     "OpenAI-style API key"),
    (r'ghp_[a-zA-Z0-9]{36}', ThreatCategory.CREDENTIAL_EXPOSURE, ThreatLevel.DANGEROUS,
     "GitHub personal access token"),
    (r'xoxb-[a-zA-Z0-9-]+', ThreatCategory.CREDENTIAL_EXPOSURE, ThreatLevel.DANGEROUS,
     "Slack bot token"),

    # === PERSISTENCE ===
    (r'crontab\s+-[el]', ThreatCategory.PERSISTENCE, ThreatLevel.CAUTION,
     "crontab modification"),
    (r'(?:\.bashrc|\.zshrc|\.profile|\.bash_profile)\s*>>', ThreatCategory.PERSISTENCE, ThreatLevel.CAUTION,
     "shell rc file modification"),
    (r'authorized_keys', ThreatCategory.PERSISTENCE, ThreatLevel.DANGEROUS,
     "SSH authorized_keys modification"),
    (r'systemctl\s+(?:enable|start)', ThreatCategory.PERSISTENCE, ThreatLevel.CAUTION,
     "systemd service activation"),
    (r'launchctl\s+load', ThreatCategory.PERSISTENCE, ThreatLevel.CAUTION,
     "macOS launchd persistence"),

    # === PRIVILEGE ESCALATION ===
    (r'sudo\s+(?!apt\s|brew\s|yum\s)', ThreatCategory.PRIVILEGE_ESCALATION, ThreatLevel.CAUTION,
     "sudo usage (non-package-manager)"),
    (r'chmod\s+[47]755\s', ThreatCategory.PRIVILEGE_ESCALATION, ThreatLevel.CAUTION,
     "setuid bit modification"),
    (r'chown\s+root', ThreatCategory.PRIVILEGE_ESCALATION, ThreatLevel.CAUTION,
     "chown to root"),
]

# Compile patterns once
_COMPILED_PATTERNS = [
    (re.compile(pat, re.IGNORECASE | re.MULTILINE), cat, level, desc)
    for pat, cat, level, desc in _PATTERNS
]

# Invisible unicode ranges (zero-width, format control, etc.)
_INVISIBLE_UNICODE_RE = re.compile(r'[\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufeff\u0000-\u0008\u000b\u000c\u000e-\u001f]')


# ---------------------------------------------------------------------------
# Security scanning
# ---------------------------------------------------------------------------

def scan_skill(content: str, source: str = "agent-created") -> ScanResult:
    """Scan skill content for security threats.

    Args:
        content: The full SKILL.md content (frontmatter + instructions)
        source: Trust source — "builtin", "agent-created", or "community"

    Returns:
        ScanResult with findings and pass/fail status based on trust policy.
    """
    findings: List[Finding] = []
    lines = content.split('\n')

    # Check each compiled pattern against each line
    for line_num, line in enumerate(lines, 1):
        for regex, category, level, description in _COMPILED_PATTERNS:
            for m in regex.finditer(line):
                findings.append(Finding(
                    category=category,
                    level=level,
                    pattern=regex.pattern,
                    match=m.group()[:200],
                    line_number=line_num,
                    description=description,
                ))

    # Invisible unicode check (full content)
    for m in _INVISIBLE_UNICODE_RE.finditer(content):
        pos = content[:m.start()].count('\n') + 1
        findings.append(Finding(
            category=ThreatCategory.INVISIBLE_UNICODE,
            level=ThreatLevel.CAUTION,
            pattern="invisible_unicode",
            match=repr(m.group()),
            line_number=pos,
            description=f"Invisible unicode character: U+{ord(m.group()):04X}",
        ))

    # Determine max threat level
    max_level = ThreatLevel.SAFE
    for f in findings:
        if f.level == ThreatLevel.DANGEROUS:
            max_level = ThreatLevel.DANGEROUS
            break
        if f.level == ThreatLevel.CAUTION:
            max_level = ThreatLevel.CAUTION

    # Check against trust policy
    allowed_levels = TRUST_POLICIES.get(source, TRUST_POLICIES["community"])
    passed = max_level in allowed_levels

    # Build summary
    if not findings:
        summary = "No threats detected"
    else:
        counts = {}
        for f in findings:
            key = f"{f.level.value}:{f.category.value}"
            counts[key] = counts.get(key, 0) + 1
        parts = [f"{v}x {k}" for k, v in sorted(counts.items())]
        summary = f"{len(findings)} finding(s): {', '.join(parts)}"

    return ScanResult(
        findings=findings,
        max_threat_level=max_level,
        passed=passed,
        summary=summary,
    )


def should_allow(result: ScanResult, source: str = "agent-created") -> Tuple[bool, str]:
    """Determine if a skill should be allowed based on scan results and trust level.

    Returns:
        (allowed, reason) tuple.
    """
    if result.passed:
        return True, "Scan passed"

    allowed_levels = TRUST_POLICIES.get(source, TRUST_POLICIES["community"])
    blocked = [f for f in result.findings if f.level not in allowed_levels]

    if not blocked:
        return True, "All findings within trust policy"

    descriptions = list({f.description for f in blocked})[:5]
    return False, f"Blocked {len(blocked)} finding(s) for source '{source}': {'; '.join(descriptions)}"


# ---------------------------------------------------------------------------
# Constraints validation
# ---------------------------------------------------------------------------

MAX_SKILL_SIZE_BYTES = 15 * 1024   # 15 KB
MAX_GROWTH_RATIO = 1.20            # 20% growth cap on update


def validate_constraints(
    content: str,
    name: str,
    description: str,
    instructions: str,
    action: str = "create",
    existing_size: int = 0,
) -> ValidationResult:
    """Validate structural constraints on a skill.

    Args:
        content: Full SKILL.md content that will be written
        name: Skill name
        description: Skill description
        instructions: Skill instructions body
        action: "create" or "update"
        existing_size: Size in bytes of the current SKILL.md (for update growth check)

    Returns:
        ValidationResult with any violations.
    """
    violations: List[ConstraintViolation] = []

    # 1. Size limit
    content_size = len(content.encode('utf-8'))
    if content_size > MAX_SKILL_SIZE_BYTES:
        violations.append(ConstraintViolation(
            constraint="max_size",
            message=f"Skill size {content_size:,} bytes exceeds limit of {MAX_SKILL_SIZE_BYTES:,} bytes",
            value=content_size,
            limit=MAX_SKILL_SIZE_BYTES,
        ))

    # 2. Growth limit on update
    if action == "update" and existing_size > 0:
        max_allowed = int(existing_size * MAX_GROWTH_RATIO)
        if content_size > max_allowed:
            violations.append(ConstraintViolation(
                constraint="growth_limit",
                message=f"Update grows from {existing_size:,} to {content_size:,} bytes ({content_size/existing_size:.0%}), exceeding 20% growth limit",
                value=content_size,
                limit=max_allowed,
            ))

    # 3. Non-empty name
    if not name or not name.strip():
        violations.append(ConstraintViolation(
            constraint="non_empty_name",
            message="Skill name must not be empty",
        ))

    # 4. Non-empty description
    if not description or not description.strip():
        violations.append(ConstraintViolation(
            constraint="non_empty_description",
            message="Skill description must not be empty",
        ))

    # 5. Non-empty instructions
    if not instructions or not instructions.strip():
        violations.append(ConstraintViolation(
            constraint="non_empty_instructions",
            message="Skill instructions must not be empty",
        ))

    return ValidationResult(
        violations=violations,
        passed=len(violations) == 0,
    )
