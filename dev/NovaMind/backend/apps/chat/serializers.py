"""
Serializers for Conversation, Message, and RetrievedChunk models.
"""
from rest_framework import serializers
from .models import Conversation, Message, RetrievedChunk


class RetrievedChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = RetrievedChunk
        fields = ("id", "titre", "texte", "source_file", "score", "raw_meta")
        read_only_fields = fields


class MessageSerializer(serializers.ModelSerializer):
    retrieved_chunks = RetrievedChunkSerializer(many=True, read_only=True)
    timestamp = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Message
        fields = (
            "id",
            "role",
            "content",
            "tokens_estimate",
            "generation_info",
            "created_at",
            "timestamp",
            "retrieved_chunks",
        )
        read_only_fields = fields


class ConversationListSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ("id", "title", "message_count", "created_at", "updated_at")
        read_only_fields = fields

    def get_message_count(self, obj):
        return getattr(obj, 'message_count_annotated', obj.message_count)


class ConversationDetailSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            "id",
            "title",
            "messages",
            "message_count",
            "created_at",
            "updated_at",
            "metadata",
        )
        read_only_fields = fields

    def get_message_count(self, obj):
        # Use annotation if available (from ListView), else fall back to model property
        return getattr(obj, 'message_count_annotated', obj.message_count)


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(
        min_length=1,
        max_length=2000,
        error_messages={
            "min_length": "The question must be at least 1 character long.",
            "max_length": "The question cannot exceed 2000 characters.",
            "blank": "Question cannot be empty.",
        },
    )
    conversation_id = serializers.UUIDField(required=False, allow_null=True)


class RenameConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ("title",)
