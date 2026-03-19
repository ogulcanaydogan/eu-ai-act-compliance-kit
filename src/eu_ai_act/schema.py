"""
AI System Descriptor Schema

Pydantic models for describing AI systems in compliance with EU AI Act requirements.
These models define the structure for AI system YAML descriptors that are analyzed
by the compliance checker.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class RiskTier(str, Enum):
    """
    EU AI Act risk tier classification.

    - UNACCEPTABLE: Prohibited under Article 5 (social scoring, biometric surveillance, etc.)
    - HIGH_RISK: Subject to comprehensive requirements under Article 6 and Annex III
    - LIMITED: Subject to transparency obligations only (Article 50)
    - MINIMAL: General-purpose low-risk AI systems
    """
    UNACCEPTABLE = "unacceptable"
    HIGH_RISK = "high_risk"
    LIMITED = "limited"
    MINIMAL = "minimal"


class UseCaseDomain(str, Enum):
    """
    Primary domain/use case for the AI system.
    Aligns with Annex III of EU AI Act for high-risk category determination.
    """
    BIOMETRIC = "biometric"
    CRITICAL_INFRASTRUCTURE = "critical_infrastructure"
    LAW_ENFORCEMENT = "law_enforcement"
    EMPLOYMENT = "employment"
    CREDIT_SCORING = "credit_scoring"
    EDUCATION = "education"
    GENERAL_PURPOSE = "general_purpose"
    HEALTHCARE = "healthcare"
    CONTENT_MODERATION = "content_moderation"
    OTHER = "other"


class DataPractice(BaseModel):
    """
    Describes how data is collected, used, and managed.

    Attributes:
        type: Whether data is personal, sensitive, or other
        retention_period: How long data is retained (in days)
        sharing_third_parties: Whether data is shared with third parties
        explicit_consent: Whether explicit user consent is obtained
        anonymization: Whether data is anonymized or pseudonymized
    """
    type: str = Field(
        ...,
        description="Type of data: personal, sensitive, biometric, or other"
    )
    retention_period: int = Field(
        365,
        ge=0,
        description="Data retention period in days (0 = immediate deletion)"
    )
    sharing_third_parties: bool = Field(
        False,
        description="Whether data is shared with external third parties"
    )
    explicit_consent: bool = Field(
        False,
        description="Whether explicit user consent is obtained for data use"
    )
    anonymization: Optional[str] = Field(
        None,
        description="Anonymization/pseudonymization method used, if any"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "personal",
                "retention_period": 90,
                "sharing_third_parties": False,
                "explicit_consent": True,
                "anonymization": "k-anonymity with k=5",
            }
        }
    )


class HumanOversight(BaseModel):
    """
    Describes human oversight mechanisms for high-risk systems.

    Attributes:
        oversight_mechanism: Type of human oversight (review, approval, monitoring)
        fallback_procedure: Procedure when AI system fails or makes errors
        review_frequency: How often human review occurs
        human_authority: Whether humans can override AI decisions
    """
    oversight_mechanism: str = Field(
        ...,
        description="Type of human oversight: manual_review, approval_required, continuous_monitoring, or other"
    )
    fallback_procedure: str = Field(
        ...,
        description="Procedure for handling system failures or errors"
    )
    review_frequency: str = Field(
        ...,
        description="Frequency of human review: real_time, per_decision, daily, weekly, or other"
    )
    human_authority: bool = Field(
        True,
        description="Whether humans have authority to override or reject AI decisions"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "oversight_mechanism": "approval_required",
                "fallback_procedure": "Escalate to senior reviewer; maintain manual process",
                "review_frequency": "per_decision",
                "human_authority": True,
            }
        }
    )


class UseCase(BaseModel):
    """
    Describes a specific use case of the AI system.

    Attributes:
        domain: Primary domain from UseCaseDomain enum
        description: Detailed description of the use case
        autonomous_decision: Whether system makes autonomous decisions
        impacts_fundamental_rights: Whether decisions impact fundamental rights
        affected_population: Description of who is affected by the system
    """
    domain: UseCaseDomain = Field(
        ...,
        description="Primary use case domain"
    )
    description: str = Field(
        ...,
        min_length=10,
        description="Detailed description of the use case and functionality"
    )
    autonomous_decision: bool = Field(
        False,
        description="Whether the system makes autonomous decisions without human review"
    )
    impacts_fundamental_rights: bool = Field(
        False,
        description="Whether decisions significantly impact fundamental rights or freedoms"
    )
    affected_population: Optional[str] = Field(
        None,
        description="Description of the population affected by this system"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "domain": "employment",
                "description": "AI system analyzes job applications to shortlist candidates",
                "autonomous_decision": False,
                "impacts_fundamental_rights": True,
                "affected_population": "Job applicants in EU",
            }
        }
    )


class AISystemDescriptor(BaseModel):
    """
    Top-level descriptor for an AI system.

    This model defines the structure for describing an AI system for EU AI Act
    compliance assessment. It should be populated with accurate information about
    the system's purpose, data practices, and safeguards.

    Attributes:
        name: System name
        version: System version
        description: High-level description of the system
        use_cases: List of primary use cases
        data_practices: Data collection and management practices
        human_oversight: Human oversight mechanisms
        training_data_source: Description of training data
        documentation: Whether comprehensive documentation exists
        performance_monitoring: Whether performance is continuously monitored
        incident_procedure: Procedure for handling incidents/errors
        created_at: System creation date
        last_updated: Last update date
    """
    name: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Name of the AI system"
    )
    version: str = Field(
        "1.0.0",
        description="System version (semantic versioning)"
    )
    description: str = Field(
        ...,
        min_length=10,
        description="Comprehensive description of the AI system's purpose and functionality"
    )
    use_cases: List[UseCase] = Field(
        ...,
        min_length=1,
        description="List of primary use cases"
    )
    data_practices: List[DataPractice] = Field(
        ...,
        min_length=1,
        description="Data collection and management practices"
    )
    human_oversight: HumanOversight = Field(
        ...,
        description="Human oversight mechanisms"
    )
    training_data_source: str = Field(
        ...,
        min_length=10,
        description="Description of training data sources and quality assurance"
    )
    documentation: bool = Field(
        False,
        description="Whether comprehensive technical documentation exists"
    )
    performance_monitoring: bool = Field(
        False,
        description="Whether system performance is continuously monitored"
    )
    incident_procedure: Optional[str] = Field(
        None,
        description="Procedure for handling incidents, errors, or system failures"
    )
    created_at: Optional[datetime] = Field(
        default_factory=_utc_now,
        description="System creation timestamp"
    )
    last_updated: Optional[datetime] = Field(
        default_factory=_utc_now,
        description="Last update timestamp"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Resume Screening AI",
                "version": "2.1.0",
                "description": "AI system for automated candidate screening in recruitment",
                "use_cases": [
                    {
                        "domain": "employment",
                        "description": "Analyzes resumes and applications to identify qualified candidates",
                        "autonomous_decision": False,
                        "impacts_fundamental_rights": True,
                    }
                ],
                "data_practices": [
                    {
                        "type": "personal",
                        "retention_period": 90,
                        "sharing_third_parties": False,
                        "explicit_consent": True,
                    }
                ],
                "human_oversight": {
                    "oversight_mechanism": "approval_required",
                    "fallback_procedure": "Manual review of candidate profiles",
                    "review_frequency": "per_decision",
                    "human_authority": True,
                },
                "training_data_source": "Historical hiring data anonymized and de-identified",
                "documentation": True,
                "performance_monitoring": True,
                "incident_procedure": "Escalate to HR; disable system if accuracy drops below 85%",
            }
        }
    )


def load_system_descriptor_from_yaml(yaml_content: str) -> AISystemDescriptor:
    """
    Load an AI system descriptor from YAML content.

    Args:
        yaml_content: YAML-formatted string

    Returns:
        AISystemDescriptor instance

    Raises:
        ValueError: If YAML is invalid or schema doesn't match
    """
    data = yaml.safe_load(yaml_content)
    return AISystemDescriptor(**data)


def load_system_descriptor_from_file(filepath: str) -> AISystemDescriptor:
    """
    Load an AI system descriptor from a YAML file.

    Args:
        filepath: Path to YAML file

    Returns:
        AISystemDescriptor instance

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If YAML is invalid or schema doesn't match
    """
    with open(filepath, "r") as f:
        return load_system_descriptor_from_yaml(f.read())
