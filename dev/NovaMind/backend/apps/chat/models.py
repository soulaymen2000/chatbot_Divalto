"""
Chat models: Conversation, Message, and RetrievedChunk.
Organized for RAG workflow and historical retention.
"""
import uuid
from django.db import models
from django.conf import settings


class Conversation(models.Model):
    """A chat session belonging to one user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    title = models.CharField(max_length=255, default="New Conversation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Soft delete and custom metadata
    is_deleted = models.BooleanField(default=False)
    metadata = models.JSONField(blank=True, default=dict)

    class Meta:
        db_table = "conversations"
        ordering = ["-updated_at"]
        verbose_name = "Conversation"
        verbose_name_plural = "Conversations"

    def __str__(self):
        return f"{self.title} ({self.user.email})"

    @property
    def message_count(self):
        return self.messages.count()


class Message(models.Model):
    """A single turn in a conversation (user, assistant, or system)."""

    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    tokens_estimate = models.PositiveIntegerField(default=0)
    generation_info = models.JSONField(blank=True, default=dict)  # Stores performance timings, parameters, etc.
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "messages"
        ordering = ["created_at"]
        verbose_name = "Message"
        verbose_name_plural = "Messages"

    def __str__(self):
        return f"[{self.role.upper()}] {self.content[:60]}..."


class RetrievedChunk(models.Model):
    """A source chunk retrieved from FAISS/BM25 used to answer a query."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="retrieved_chunks",
    )
    titre = models.CharField(max_length=512)
    texte = models.TextField()
    source_file = models.CharField(max_length=1024)
    score = models.FloatField()  # Relevance score (0-1)
    raw_meta = models.JSONField(blank=True, default=dict)

    class Meta:
        db_table = "retrieved_chunks"
        verbose_name = "Retrieved Chunk"
        verbose_name_plural = "Retrieved Chunks"

    def __str__(self):
        return f"{self.titre} (Score: {self.score:.4f})"
