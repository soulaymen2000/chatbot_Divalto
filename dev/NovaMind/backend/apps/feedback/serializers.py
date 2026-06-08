"""Serializers for the feedback app."""
from rest_framework import serializers
from .models import Feedback


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = (
            "id",
            "message",
            "rating",
            "sentiment",
            "issue_type",
            "comment",
            "timestamp",
        )
        read_only_fields = ("id", "timestamp")

    def validate_rating(self, value):
        if value is not None and not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate(self, attrs):
        if not attrs.get("rating") and not attrs.get("sentiment"):
            raise serializers.ValidationError(
                "At least one of 'rating' or 'sentiment' must be provided."
            )
        return attrs


class FeedbackAnalyticsSerializer(serializers.Serializer):
    """Aggregated analytics for the admin dashboard."""
    total_feedback = serializers.IntegerField()
    avg_rating = serializers.FloatField()
    helpful_count = serializers.IntegerField()
    not_helpful_count = serializers.IntegerField()
    helpful_percent = serializers.FloatField()
    issue_breakdown = serializers.DictField()
    rating_distribution = serializers.DictField()
    recent_comments = serializers.ListField()
