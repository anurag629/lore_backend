"""
Serializers for social features (comments, interactions).
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Comment, Interaction
from apps.assets.models import IPAsset
# Note: We'll use a lightweight user serializer instead of importing from core

User = get_user_model()


class CommentUserSerializer(serializers.ModelSerializer):
    """Lightweight serializer for comment author."""
    
    class Meta:
        model = User
        fields = ['id', 'wallet_address', 'display_name', 'avatar_url']
        read_only_fields = fields


class CommentSerializer(serializers.ModelSerializer):
    """Serializer for comments."""
    
    user = CommentUserSerializer(read_only=True)
    reply_count = serializers.IntegerField(read_only=True)
    is_own_comment = serializers.SerializerMethodField()
    
    class Meta:
        model = Comment
        fields = [
            'id',
            'asset',
            'user',
            'parent',
            'content',
            'reply_count',
            'is_deleted',
            'is_own_comment',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'reply_count', 'is_own_comment']
    
    def get_is_own_comment(self, obj):
        """Check if comment belongs to current user."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.user == request.user
        return False


class CommentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating comments."""
    
    class Meta:
        model = Comment
        fields = ['asset', 'parent', 'content']
    
    def validate_content(self, value):
        """Validate comment content."""
        if not value or not value.strip():
            raise serializers.ValidationError("Comment cannot be empty.")
        if len(value) > 2000:
            raise serializers.ValidationError("Comment cannot exceed 2000 characters.")
        return value.strip()
    
    def validate(self, attrs):
        """Validate comment relationships."""
        parent = attrs.get('parent')
        asset = attrs.get('asset')
        
        if parent:
            # Ensure parent comment is on the same asset
            if parent.asset != asset:
                raise serializers.ValidationError({
                    'parent': "Reply must be on the same asset as parent comment."
                })
            # Ensure parent is not deleted
            if parent.is_deleted:
                raise serializers.ValidationError({
                    'parent': "Cannot reply to a deleted comment."
                })
        
        return attrs


class CommentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating comments."""
    
    class Meta:
        model = Comment
        fields = ['content']
    
    def validate_content(self, value):
        """Validate comment content."""
        if not value or not value.strip():
            raise serializers.ValidationError("Comment cannot be empty.")
        if len(value) > 2000:
            raise serializers.ValidationError("Comment cannot exceed 2000 characters.")
        return value.strip()


class InteractionSerializer(serializers.ModelSerializer):
    """Serializer for interactions."""
    
    user = CommentUserSerializer(read_only=True)
    
    class Meta:
        model = Interaction
        fields = ['id', 'user', 'asset', 'type', 'created_at']
        read_only_fields = fields

