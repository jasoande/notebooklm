#!/usr/bin/env python3
"""
Project APE - Output Validation Framework
Quality checks for LLM-generated content
"""
import logging
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable


@dataclass
class ValidationIssue:
    """Represents a single validation issue."""
    severity: str  # "error", "warning", "info"
    rule: str
    message: str
    context: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of validating output."""
    is_valid: bool
    quality_score: float  # 0-10 scale
    issues: List[ValidationIssue]
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    def has_warnings(self) -> bool:
        return any(issue.severity == "warning" for issue in self.issues)

    def get_summary(self) -> str:
        """Get human-readable summary."""
        error_count = sum(1 for i in self.issues if i.severity == "error")
        warning_count = sum(1 for i in self.issues if i.severity == "warning")

        if self.is_valid:
            return f"✓ Valid (Score: {self.quality_score:.1f}/10, {warning_count} warnings)"
        else:
            return f"✗ Invalid (Score: {self.quality_score:.1f}/10, {error_count} errors, {warning_count} warnings)"


class PromptValidator:
    """Base validator for prompt outputs."""

    def __init__(self, prompt_id: str, config: Dict):
        self.prompt_id = prompt_id
        self.config = config
        self.issues: List[ValidationIssue] = []

    def validate(self, output: str, metadata: Dict = None) -> ValidationResult:
        """Run all validation checks."""
        self.issues = []
        metadata = metadata or {}

        # Run standard checks
        self._check_word_count(output)
        self._check_required_sections(output)
        self._check_citations(output)
        self._check_hallucination_indicators(output)
        self._check_forbidden_phrases(output)

        # Calculate quality score
        quality_score = self._calculate_quality_score(output)

        # Determine if valid (no errors)
        is_valid = not any(issue.severity == "error" for issue in self.issues)

        return ValidationResult(
            is_valid=is_valid,
            quality_score=quality_score,
            issues=self.issues,
            metadata=metadata
        )

    def _add_issue(self, severity: str, rule: str, message: str, context: str = None):
        """Add validation issue."""
        self.issues.append(ValidationIssue(
            severity=severity,
            rule=rule,
            message=message,
            context=context
        ))

    def _check_word_count(self, output: str):
        """Check if output meets word count requirements."""
        words = len(output.split())

        min_words = self.config.get("min_words", 0)
        max_words = self.config.get("max_words", float('inf'))

        if words < min_words:
            self._add_issue(
                "error",
                "word_count",
                f"Output too short: {words} words < {min_words} minimum",
                f"Word count: {words}"
            )
        elif words > max_words:
            self._add_issue(
                "warning",
                "word_count",
                f"Output too long: {words} words > {max_words} maximum",
                f"Word count: {words}"
            )

    def _check_required_sections(self, output: str):
        """Check if all required sections are present."""
        required_sections = self.config.get("required_sections", [])

        for section in required_sections:
            # Check for section header (markdown or bold)
            patterns = [
                rf"^#+\s*{re.escape(section)}", # Markdown header
                rf"\*\*{re.escape(section)}\*\*", # Bold
                rf"^{re.escape(section)}:", # Colon-prefixed
            ]

            found = any(
                re.search(pattern, output, re.MULTILINE | re.IGNORECASE)
                for pattern in patterns
            )

            if not found:
                self._add_issue(
                    "error",
                    "missing_section",
                    f"Required section missing: '{section}'",
                    None
                )

    def _check_citations(self, output: str):
        """Check citation requirements."""
        min_citations = self.config.get("min_citations", 0)

        # Count citations in various formats
        citation_patterns = [
            r'\[Source:\s*[^\]]+\]',  # [Source: ...]
            r'\[https?://[^\]]+\]',   # [http://...]
            r'\(Source:\s*[^)]+\)',   # (Source: ...)
        ]

        citation_count = sum(
            len(re.findall(pattern, output, re.IGNORECASE))
            for pattern in citation_patterns
        )

        if citation_count < min_citations:
            self._add_issue(
                "warning" if min_citations <= 5 else "error",
                "insufficient_citations",
                f"Insufficient citations: {citation_count} < {min_citations} required",
                f"Found {citation_count} citations"
            )

    def _check_hallucination_indicators(self, output: str):
        """Check for phrases that suggest hallucination or speculation."""
        hallucination_phrases = [
            "likely", "probably", "appears to", "seems to",
            "may be", "might be", "could be", "possibly",
            "estimated to be", "believed to be", "thought to be",
            "allegedly", "reportedly", "supposedly"
        ]

        for phrase in hallucination_phrases:
            pattern = r'\b' + re.escape(phrase) + r'\b'
            matches = list(re.finditer(pattern, output, re.IGNORECASE))

            if matches:
                # Extract context around match
                for match in matches[:3]:  # Limit to first 3 instances
                    start = max(0, match.start() - 40)
                    end = min(len(output), match.end() + 40)
                    context = output[start:end]

                    self._add_issue(
                        "warning",
                        "hallucination_indicator",
                        f"Speculative language detected: '{phrase}'",
                        f"...{context}..."
                    )

    def _check_forbidden_phrases(self, output: str):
        """Check for explicitly forbidden phrases."""
        forbidden = self.config.get("forbidden_phrases", [])

        for phrase in forbidden:
            if phrase.lower() in output.lower():
                self._add_issue(
                    "error",
                    "forbidden_phrase",
                    f"Forbidden phrase detected: '{phrase}'",
                    None
                )

    def _calculate_quality_score(self, output: str) -> float:
        """Calculate quality score (0-10 scale)."""
        score = 10.0

        # Deduct points for issues
        for issue in self.issues:
            if issue.severity == "error":
                score -= 2.0
            elif issue.severity == "warning":
                score -= 0.5

        # Bonus for high citation count (if expected)
        min_citations = self.config.get("min_citations", 0)
        if min_citations > 0:
            citations = len(re.findall(r'\[Source:', output))
            if citations > min_citations * 1.5:
                score += 0.5  # Bonus for thorough research

        # Ensure score is in valid range
        return max(0.0, min(10.0, score))


# ==============================================================================
# PROMPT-SPECIFIC VALIDATORS
# ==============================================================================

class FoundationResearchValidator(PromptValidator):
    """Validator for foundation research prompt."""

    def __init__(self):
        super().__init__("foundation_research", {
            "min_words": 800,
            "max_words": 1500,
            "min_citations": 10,
            "required_sections": [
                "Company Snapshot",
                "Recent Strategic Developments",
                "Financial Health",
                "Technology Posture"
            ]
        })


class BusinessObjectivesValidator(PromptValidator):
    """Validator for business objectives prompt."""

    def __init__(self):
        super().__init__("business_objectives", {
            "min_words": 400,
            "max_words": 700,
            "min_citations": 3,
            "required_sections": [
                "Executive Summary",
                "Top 3 Business Objectives",
                "Top Business Challenges"
            ]
        })


class ValuePropositionsValidator(PromptValidator):
    """Validator for value propositions prompt."""

    def __init__(self):
        super().__init__("value_propositions", {
            "min_words": 800,
            "max_words": 1500,
            "min_citations": 2,
            "required_sections": [
                "ISSUE",
                "RED HAT ACTION",
                "MEASURABLE VALUE"
            ]
        })

    def validate(self, output: str, metadata: Dict = None) -> ValidationResult:
        """Override to add custom checks."""
        result = super().validate(output, metadata)

        # Check for Red Hat product mentions
        rh_products = ["RHEL", "OpenShift", "Ansible", "Red Hat"]
        product_mentions = sum(
            output.count(product) for product in rh_products
        )

        if product_mentions < 3:
            self._add_issue(
                "warning",
                "product_mentions",
                f"Few Red Hat product mentions: {product_mentions} < 3",
                None
            )

        # Recalculate score with new issues
        result.quality_score = self._calculate_quality_score(output)
        result.is_valid = not result.has_errors()

        return result


# ==============================================================================
# VALIDATOR FACTORY
# ==============================================================================

VALIDATOR_MAP = {
    "foundation_research": FoundationResearchValidator,
    "ask_01": FoundationResearchValidator,  # Alias
    "business_objectives": BusinessObjectivesValidator,
    "chat_01": BusinessObjectivesValidator,  # Alias
    "value_propositions": ValuePropositionsValidator,
    "chat_04": ValuePropositionsValidator,  # Alias
}


def get_validator(prompt_id: str) -> Optional[PromptValidator]:
    """Get validator for prompt ID."""
    # Normalize prompt ID
    prompt_id_normalized = prompt_id.lower().replace("_", "").replace("-", "")

    # Try exact match
    for key, validator_class in VALIDATOR_MAP.items():
        if key.replace("_", "").replace("-", "") in prompt_id_normalized:
            return validator_class()

    # Default: generic validator with minimal requirements
    return PromptValidator(prompt_id, {
        "min_words": 100,
        "max_words": 10000,
        "min_citations": 0,
        "required_sections": []
    })


def validate_output(prompt_id: str, output: str, metadata: Dict = None) -> ValidationResult:
    """Validate output for given prompt."""
    validator = get_validator(prompt_id)
    result = validator.validate(output, metadata)

    # Log validation result
    if result.has_errors():
        logging.error(f"[{prompt_id}] Validation FAILED: {result.get_summary()}")
        for issue in result.issues:
            if issue.severity == "error":
                logging.error(f"  - {issue.rule}: {issue.message}")
    elif result.has_warnings():
        logging.warning(f"[{prompt_id}] Validation passed with warnings: {result.get_summary()}")
        for issue in result.issues:
            if issue.severity == "warning":
                logging.warning(f"  - {issue.rule}: {issue.message}")
    else:
        logging.info(f"[{prompt_id}] Validation PASSED: {result.get_summary()}")

    return result
