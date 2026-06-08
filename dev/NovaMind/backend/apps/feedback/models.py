"""
Feedback model — stores user ratings and comments on AI responses.
Used to track quality, detect recurring failures, and improve prompts.
"""
import uuid
from django.db import models
from django.conf import settings


class Feedback(models.Model):
    SENTIMENT_CHOICES = [
        ("helpful", "Helpful"),
        ("not_helpful", "Not Helpful"),
    ]

    ISSUE_TYPE_CHOICES = [
        ("incorrect", "Incorrect Information"),
        ("incomplete", "Incomplete Answer"),
        ("too_long", "Too Long"),
        ("too_short", "Too Short"),
        ("off_topic", "Off Topic"),
        ("harmful", "Harmful Content"),
        ("other", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feedbacks",
    )
    message = models.OneToOneField(
        "chat.Message",
        on_delete=models.CASCADE,
        related_name="feedback",
    )
    conversation = models.ForeignKey(
        "chat.Conversation",
        on_delete=models.CASCADE,
        related_name="feedbacks",
    )

    # Feedback data
    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Star rating 1–5",
    )
    sentiment = models.CharField(
        max_length=15,
        choices=SENTIMENT_CHOICES,
        null=True,
        blank=True,
    )
    issue_type = models.CharField(
        max_length=20,
        choices=ISSUE_TYPE_CHOICES,
        null=True,
        blank=True,
    )
    comment = models.TextField(blank=True, default="")

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "feedback"
        ordering = ["-timestamp"]
        verbose_name = "Feedback"
        verbose_name_plural = "Feedback"

    def __str__(self):
        return f"Feedback by {self.user.email} — {self.sentiment or 'unrated'} ({self.rating}★)"
