"""
Feedback views.
Users submit feedback on assistant messages.
Admins can view aggregated analytics.
"""
import logging
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from apps.chat.models import Message
from .models import Feedback
from .serializers import FeedbackSerializer, FeedbackAnalyticsSerializer

logger = logging.getLogger("apps.feedback")


class MessageFeedbackView(APIView):
    """
    POST /api/messages/{message_id}/feedback/
    — Submit or update feedback on an assistant message.
    Only the owner of the conversation can submit feedback.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, message_id):
        message = get_object_or_404(
            Message,
            pk=message_id,
            role="assistant",
            conversation__user=request.user,
        )

        # Update if feedback already exists (idempotent)
        existing = Feedback.objects.filter(message=message).first()
        if existing:
            serializer = FeedbackSerializer(existing, data=request.data, partial=True)
        else:
            serializer = FeedbackSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(
                user=request.user,
                message=message,
                conversation=message.conversation,
            )
            logger.info(
                "Feedback submitted by %s for message %s",
                request.user.email,
                message_id,
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FeedbackAnalyticsView(APIView):
    """
    GET /api/admin/feedback/analytics/
    — Aggregated feedback stats (admin only).
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = Feedback.objects.all()
        total = qs.count()

        if total == 0:
            return Response({
                "total_feedback": 0,
                "avg_rating": 0,
                "helpful_count": 0,
                "not_helpful_count": 0,
                "helpful_percent": 0,
                "issue_breakdown": {},
                "rating_distribution": {},
                "recent_comments": [],
            })

        avg_rating = qs.filter(rating__isnull=False).aggregate(avg=Avg("rating"))["avg"] or 0
        helpful_count = qs.filter(sentiment="helpful").count()
        not_helpful_count = qs.filter(sentiment="not_helpful").count()
        helpful_percent = round((helpful_count / total) * 100, 1) if total else 0

        # Issue type breakdown
        issue_counts = (
            qs.exclude(issue_type__isnull=True)
            .exclude(issue_type="")
            .values("issue_type")
            .annotate(count=Count("id"))
        )
        issue_breakdown = {item["issue_type"]: item["count"] for item in issue_counts}

        # Rating distribution (1–5)
        rating_dist = {}
        for i in range(1, 6):
            rating_dist[str(i)] = qs.filter(rating=i).count()

        # 10 most recent comments
        recent_comments = list(
            qs.exclude(comment="")
            .order_by("-timestamp")
            .values("comment", "sentiment", "rating", "timestamp")[:10]
        )

        return Response({
            "total_feedback": total,
            "avg_rating": round(avg_rating, 2),
            "helpful_count": helpful_count,
            "not_helpful_count": not_helpful_count,
            "helpful_percent": helpful_percent,
            "issue_breakdown": issue_breakdown,
            "rating_distribution": rating_dist,
            "recent_comments": recent_comments,
        })
