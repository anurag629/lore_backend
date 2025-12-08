"""
Copyright/Plagiarism Detection Agent

Analyzes IP assets for potential copyright issues using:
- Perceptual image hashing (detect modified/cropped copies)
- Text similarity analysis (TF-IDF, cosine similarity)
- Risk level assessment
- Actionable recommendations
"""
import logging
from typing import Dict, Any, List, Optional, Tuple
import io
from PIL import Image
import imagehash
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import requests
from django.core.files.storage import default_storage
from django.db.models import Q

from apps.assets.models import IPAsset
from apps.ai.models import CopyrightAnalysisResult
from .base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)


class CopyrightAgent(BaseAgent):
    """
    Agent for detecting potential copyright infringement.

    Uses multiple techniques:
    1. Perceptual hashing for image similarity
    2. Text similarity for descriptions/titles
    3. Combined risk assessment
    """

    # Thresholds for similarity detection
    IMAGE_HASH_THRESHOLD = 10  # Hamming distance threshold
    TEXT_SIMILARITY_THRESHOLD = 0.75  # Cosine similarity threshold

    def get_name(self) -> str:
        return "CopyrightAgent"

    def analyze(self, asset_id: int, **kwargs) -> AgentResult:
        """
        Analyze an asset for potential copyright issues.

        Args:
            asset_id: ID of the IPAsset to analyze

        Returns:
            AgentResult with copyright analysis data
        """
        # Validate input
        error = self.validate_input(['asset_id'], asset_id=asset_id)
        if error:
            return AgentResult(
                success=False,
                data={},
                confidence=0.0,
                errors=[error]
            )

        try:
            # Get the asset
            asset = IPAsset.objects.select_related('creator').get(id=asset_id)
        except IPAsset.DoesNotExist:
            return AgentResult(
                success=False,
                data={},
                confidence=0.0,
                errors=[f"Asset with id {asset_id} not found"]
            )

        # Perform analysis
        potential_matches = []
        warnings = []

        # 1. Image similarity analysis (if asset has image)
        if asset.media_url:
            image_matches = self._analyze_image_similarity(asset)
            potential_matches.extend(image_matches)

        # 2. Text similarity analysis (title + description)
        text_matches = self._analyze_text_similarity(asset)
        potential_matches.extend(text_matches)

        # 3. Deduplicate and rank matches
        unique_matches = self._deduplicate_matches(potential_matches)

        # 4. Calculate risk level
        risk_level, similarity_score = self._calculate_risk(unique_matches)

        # 5. Generate recommendations
        recommendations = self._generate_recommendations(
            risk_level,
            unique_matches,
            asset
        )

        # 6. Determine if likely original
        is_likely_original = risk_level == 'low' and similarity_score < 0.3

        # 7. Calculate confidence
        confidence = self._calculate_confidence(asset, unique_matches)

        # Build result data
        data = {
            'is_likely_original': is_likely_original,
            'similarity_score': similarity_score,
            'risk_level': risk_level,
            'potential_matches': unique_matches[:10],  # Top 10 matches
            'recommendations': recommendations,
            'confidence': confidence,
            'analysis_details': {
                'total_matches_found': len(unique_matches),
                'image_analysis_performed': bool(asset.media_url),
                'text_analysis_performed': True,
            }
        }

        # Save result to database
        CopyrightAnalysisResult.objects.update_or_create(
            asset=asset,
            defaults={
                'is_likely_original': is_likely_original,
                'similarity_score': similarity_score,
                'risk_level': risk_level,
                'potential_matches': unique_matches[:10],
                'recommendations': recommendations,
                'confidence': confidence,
            }
        )

        return AgentResult(
            success=True,
            data=data,
            confidence=confidence,
            warnings=warnings
        )

    def _analyze_image_similarity(self, asset: IPAsset) -> List[Dict[str, Any]]:
        """
        Analyze image similarity using perceptual hashing.

        Args:
            asset: The asset to analyze

        Returns:
            List of potential matches with similarity scores
        """
        matches = []

        try:
            # Download and hash the image
            asset_hash = self._get_image_hash(asset.media_url)
            if not asset_hash:
                return matches

            # Compare with other assets (exclude derivatives of this asset)
            other_assets = IPAsset.objects.filter(
                file_url__isnull=False
            ).exclude(
                id=asset.id
            ).exclude(
                parent_asset=asset
            )[:1000]  # Limit to recent 1000 assets for performance

            for other_asset in other_assets:
                try:
                    other_hash = self._get_image_hash(other_asset.media_url)
                    if not other_hash:
                        continue

                    # Calculate Hamming distance
                    distance = asset_hash - other_hash

                    # If similar enough, add as potential match
                    if distance <= self.IMAGE_HASH_THRESHOLD:
                        similarity = 1.0 - (distance / 64.0)  # Normalize to 0-1
                        matches.append({
                            'asset_id': other_asset.id,
                            'asset_title': other_asset.title,
                            'asset_creator': other_asset.creator.display_name if other_asset.creator else 'Unknown',
                            'similarity_score': round(similarity, 3),
                            'match_type': 'image',
                            'hamming_distance': distance
                        })

                except Exception as e:
                    logger.warning(f"Error comparing with asset {other_asset.id}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in image similarity analysis: {e}")

        return sorted(matches, key=lambda x: x['similarity_score'], reverse=True)

    def _analyze_text_similarity(self, asset: IPAsset) -> List[Dict[str, Any]]:
        """
        Analyze text similarity using TF-IDF and cosine similarity.

        Args:
            asset: The asset to analyze

        Returns:
            List of potential matches with similarity scores
        """
        matches = []

        try:
            # Combine title and description
            asset_text = f"{asset.title} {asset.description or ''}"

            if len(asset_text.strip()) < 10:
                return matches  # Not enough text to analyze

            # Get other assets for comparison
            other_assets = IPAsset.objects.exclude(
                id=asset.id
            ).exclude(
                parent_asset=asset
            ).values('id', 'title', 'description', 'creator__display_name')[:1000]

            if not other_assets:
                return matches

            # Prepare corpus
            corpus = [asset_text]
            asset_map = []

            for other in other_assets:
                other_text = f"{other['title']} {other['description'] or ''}"
                if len(other_text.strip()) >= 10:
                    corpus.append(other_text)
                    asset_map.append(other)

            if len(corpus) < 2:
                return matches

            # Calculate TF-IDF vectors
            vectorizer = TfidfVectorizer(
                max_features=500,
                stop_words='english',
                ngram_range=(1, 2)
            )
            tfidf_matrix = vectorizer.fit_transform(corpus)

            # Calculate cosine similarity
            similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()

            # Find high similarity matches
            for idx, similarity in enumerate(similarities):
                if similarity >= self.TEXT_SIMILARITY_THRESHOLD:
                    other = asset_map[idx]
                    matches.append({
                        'asset_id': other['id'],
                        'asset_title': other['title'],
                        'asset_creator': other['creator__display_name'] or 'Unknown',
                        'similarity_score': round(float(similarity), 3),
                        'match_type': 'text',
                    })

        except Exception as e:
            logger.error(f"Error in text similarity analysis: {e}")

        return sorted(matches, key=lambda x: x['similarity_score'], reverse=True)

    def _get_image_hash(self, image_url: str) -> Optional[imagehash.ImageHash]:
        """
        Get perceptual hash of an image.

        Args:
            image_url: URL or path to image

        Returns:
            ImageHash object or None if failed
        """
        try:
            # Handle both URLs and file paths
            if image_url.startswith('http'):
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()
                image = Image.open(io.BytesIO(response.content))
            else:
                # Local file in storage
                with default_storage.open(image_url, 'rb') as f:
                    image = Image.open(f)
                    image.load()  # Force load to prevent file closure issues

            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Calculate perceptual hash (average hash)
            return imagehash.average_hash(image)

        except Exception as e:
            logger.warning(f"Error hashing image {image_url}: {e}")
            return None

    def _deduplicate_matches(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate matches by asset_id, keeping the highest similarity score.

        Args:
            matches: List of match dictionaries

        Returns:
            Deduplicated list of matches
        """
        seen = {}
        for match in matches:
            asset_id = match['asset_id']
            if asset_id not in seen or match['similarity_score'] > seen[asset_id]['similarity_score']:
                seen[asset_id] = match

        return sorted(seen.values(), key=lambda x: x['similarity_score'], reverse=True)

    def _calculate_risk(self, matches: List[Dict[str, Any]]) -> Tuple[str, float]:
        """
        Calculate overall risk level and similarity score.

        Args:
            matches: List of potential matches

        Returns:
            Tuple of (risk_level, max_similarity_score)
        """
        if not matches:
            return 'low', 0.0

        max_similarity = matches[0]['similarity_score']
        high_similarity_count = sum(1 for m in matches if m['similarity_score'] >= 0.85)

        # Determine risk level
        if max_similarity >= 0.95 or high_similarity_count >= 3:
            risk_level = 'high'
        elif max_similarity >= 0.75 or high_similarity_count >= 1:
            risk_level = 'medium'
        else:
            risk_level = 'low'

        return risk_level, max_similarity

    def _generate_recommendations(
        self,
        risk_level: str,
        matches: List[Dict[str, Any]],
        asset: IPAsset
    ) -> List[str]:
        """
        Generate actionable recommendations based on analysis.

        Args:
            risk_level: Calculated risk level
            matches: List of potential matches
            asset: The asset being analyzed

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if risk_level == 'high':
            recommendations.append(
                "⚠️ HIGH RISK: This asset appears very similar to existing content. "
                "We strongly recommend reviewing the flagged matches before minting."
            )
            if matches:
                top_match = matches[0]
                recommendations.append(
                    f"Most similar asset: '{top_match['asset_title']}' "
                    f"({top_match['similarity_score']*100:.1f}% similar)"
                )
            recommendations.append(
                "Action: Verify you have the right to use this content, or consider "
                "significant modifications to make it more original."
            )

        elif risk_level == 'medium':
            recommendations.append(
                "⚡ MEDIUM RISK: Some similarity detected with existing content. "
                "Please review the matches and ensure your work is sufficiently original."
            )
            recommendations.append(
                "Action: Consider adding unique elements or verifying this is a legitimate derivative."
            )

        else:
            recommendations.append(
                "✅ LOW RISK: No significant similarity detected with existing content."
            )
            recommendations.append(
                "Your asset appears to be original. You may proceed with minting."
            )

        # Additional recommendations
        if not asset.description or len(asset.description) < 50:
            recommendations.append(
                "Tip: Add a detailed description to help prove originality."
            )

        if matches and asset.parent_asset_id is None:
            recommendations.append(
                "If this is a derivative work, make sure to properly attribute the parent asset."
            )

        return recommendations

    def _calculate_confidence(
        self,
        asset: IPAsset,
        matches: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate confidence score for the analysis.

        Args:
            asset: The asset being analyzed
            matches: List of matches found

        Returns:
            Confidence score between 0.0 and 1.0
        """
        confidence = 0.5  # Base confidence

        # Increase confidence if we have image data
        if asset.media_url:
            confidence += 0.2

        # Increase confidence if we have text data
        if asset.description and len(asset.description) >= 50:
            confidence += 0.2

        # Increase confidence if we found clear matches or clear non-matches
        if matches:
            max_sim = matches[0]['similarity_score']
            if max_sim > 0.9 or max_sim < 0.3:
                confidence += 0.1
        else:
            confidence += 0.1  # High confidence in originality

        return min(confidence, 1.0)
