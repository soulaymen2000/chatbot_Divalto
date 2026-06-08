"""URL patterns for the feedback app."""
from django.urls import path
from .views import MessageFeedbackView, FeedbackAnalyticsView

urlpatterns = [
    path(
        "messages/<uuid:message_id>/feedback/",
        MessageFeedbackView.as_view(),
        name="message-feedback",
    ),
    path(
        "admin/feedback/analytics/",
        FeedbackAnalyticsView.as_view(),
        name="feedback-analytics",
    ),
]
