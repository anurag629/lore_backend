"""
Database models for storing AI agent analysis results.

These models store the results of various AI agents analyzing IP assets.
"""
from django.db import models
from django.contrib.postgres.fields import ArrayField
from apps.assets.models import IPAsset


class CopyrightAnalysisResult(models.Model):
    """
    Stores copyright/plagiarism detection results.

    Used to identify potential copyright issues before minting.
    """
    asset = models.OneToOneField(
        IPAsset,
        on_delete=models.CASCADE,
        related_name='copyright_analysis',
        help_text="Asset being analyzed"
    )

    is_likely_original = models.BooleanField(
        default=True,
        help_text="Whether the asset appears to be original content"
    )

    similarity_score = models.FloatField(
        default=0.0,
        help_text="Overall similarity score (0.0-1.0)"
    )

    risk_level = models.CharField(
        max_length=20,
        choices=[
            ('low', 'Low Risk'),
            ('medium', 'Medium Risk'),
            ('high', 'High Risk'),
        ],
        default='low',
        help_text="Copyright risk assessment"
    )

    potential_matches = models.JSONField(
        default=list,
        help_text="List of potential matching assets"
    )

    recommendations = models.JSONField(
        default=list,
        help_text="Actionable recommendations for the creator"
    )

    confidence = models.FloatField(
        default=1.0,
        help_text="Confidence in the analysis (0.0-1.0)"
    )

    processing_time = models.FloatField(
        default=0.0,
        help_text="Time taken for analysis in seconds"
    )

    analyzed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the analysis was performed"
    )

    class Meta:
        verbose_name = "Copyright Analysis Result"
        verbose_name_plural = "Copyright Analysis Results"
        ordering = ['-analyzed_at']

    def __str__(self):
        return f"Copyright Analysis: {self.asset.title} ({self.risk_level})"


class QualityAnalysisResult(models.Model):
    """
    Stores quality scoring results.

    Analyzes technical quality, description quality, and market appeal.
    """
    asset = models.OneToOneField(
        IPAsset,
        on_delete=models.CASCADE,
        related_name='quality_analysis',
        help_text="Asset being analyzed"
    )

    overall_score = models.FloatField(
        help_text="Overall quality score (0-100)"
    )

    technical_quality = models.JSONField(
        help_text="Technical quality metrics (resolution, sharpness, etc.)"
    )

    description_quality = models.JSONField(
        help_text="Description quality metrics (length, clarity, SEO)"
    )

    metadata_completeness = models.FloatField(
        help_text="Completeness of metadata (0-100)"
    )

    market_appeal = models.FloatField(
        help_text="Predicted market appeal (0-100)"
    )

    improvement_suggestions = models.JSONField(
        default=list,
        help_text="Suggestions for improving quality"
    )

    strengths = models.JSONField(
        default=list,
        help_text="Identified strengths of the asset"
    )

    confidence = models.FloatField(
        default=1.0,
        help_text="Confidence in the analysis (0.0-1.0)"
    )

    processing_time = models.FloatField(
        default=0.0,
        help_text="Time taken for analysis in seconds"
    )

    analyzed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the analysis was performed"
    )

    class Meta:
        verbose_name = "Quality Analysis Result"
        verbose_name_plural = "Quality Analysis Results"
        ordering = ['-analyzed_at']

    def __str__(self):
        return f"Quality Analysis: {self.asset.title} (score: {self.overall_score:.1f})"


class PricingAnalysisResult(models.Model):
    """
    Stores smart pricing recommendations.

    Suggests royalty percentages based on market analysis.
    """
    asset = models.OneToOneField(
        IPAsset,
        on_delete=models.CASCADE,
        related_name='pricing_analysis',
        help_text="Asset being analyzed"
    )

    suggested_tiers = models.JSONField(
        help_text="Three pricing tiers (conservative, balanced, aggressive)"
    )

    market_average = models.FloatField(
        help_text="Market average royalty percentage"
    )

    similar_assets_count = models.IntegerField(
        default=0,
        help_text="Number of similar assets analyzed"
    )

    demand_prediction = models.FloatField(
        help_text="Predicted demand score (0-100)"
    )

    confidence = models.FloatField(
        default=1.0,
        help_text="Confidence in the recommendations (0.0-1.0)"
    )

    reasoning = models.TextField(
        help_text="Explanation of pricing recommendations"
    )

    processing_time = models.FloatField(
        default=0.0,
        help_text="Time taken for analysis in seconds"
    )

    analyzed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the analysis was performed"
    )

    class Meta:
        verbose_name = "Pricing Analysis Result"
        verbose_name_plural = "Pricing Analysis Results"
        ordering = ['-analyzed_at']

    def __str__(self):
        return f"Pricing Analysis: {self.asset.title}"


class ValidationWorkflowResult(models.Model):
    """
    Stores results from multi-agent pre-mint validation workflow.

    Combines results from multiple agents for comprehensive validation.
    """
    asset = models.OneToOneField(
        IPAsset,
        on_delete=models.CASCADE,
        related_name='validation_result',
        help_text="Asset being validated"
    )

    workflow_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('running', 'Running'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='pending',
        help_text="Overall workflow status"
    )

    steps_completed = models.JSONField(
        default=list,
        help_text="List of completed validation steps"
    )

    overall_verdict = models.CharField(
        max_length=20,
        choices=[
            ('approved', 'Approved'),
            ('warning', 'Approved with Warnings'),
            ('rejected', 'Rejected'),
        ],
        null=True,
        blank=True,
        help_text="Final recommendation"
    )

    agent_results = models.JSONField(
        default=dict,
        help_text="Results from each agent"
    )

    warnings = models.JSONField(
        default=list,
        help_text="Warnings raised during validation"
    )

    blockers = models.JSONField(
        default=list,
        help_text="Issues that should block minting"
    )

    total_processing_time = models.FloatField(
        default=0.0,
        help_text="Total time for all agents"
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When validation started"
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When validation completed"
    )

    class Meta:
        verbose_name = "Validation Workflow Result"
        verbose_name_plural = "Validation Workflow Results"
        ordering = ['-started_at']

    def __str__(self):
        return f"Validation: {self.asset.title} ({self.workflow_status})"
