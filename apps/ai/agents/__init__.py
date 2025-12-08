"""
AI Agents for IP Asset Analysis

Provides intelligent analysis and recommendations for IP assets including:
- Copyright/plagiarism detection
- Quality scoring
- Smart pricing recommendations
- Permission suggestions
"""

from .base_agent import BaseAgent, AgentResult
from .copyright_agent import CopyrightAgent
from .quality_agent import QualityAgent
from .pricing_agent import PricingAgent

__all__ = [
    'BaseAgent',
    'AgentResult',
    'CopyrightAgent',
    'QualityAgent',
    'PricingAgent',
]
