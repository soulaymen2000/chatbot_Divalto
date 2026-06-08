"""
Chat App Views.
Implements highly optimized endpoints for RAG execution, conversation management,
soft-delete cleanups, and title generation, complete with transaction control and performance logging.
"""
import time
import logging
from django.db import transaction
from django.conf import settings
from django.shortcuts import get_object_or_404
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from django.utils import timezone
from datetime import timedelta

from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from .models import Conversation, Message, RetrievedChunk
from .serializers import (
    ConversationListSerializer,
    ConversationDetailSerializer,
    MessageSerializer,
    SendMessageSerializer,
    RenameConversationSerializer,
)
from .services.rag import RAGPipeline
from .services.title_generator import generate_conversation_title

logger = logging.getLogger("apps.chat")


class CustomPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ─── 1. POST /api/chat/ask/ ──────────────────────────────────────────────────

@method_decorator(
    ratelimit(key="user", rate=settings.RATE_LIMIT_ASK, method="POST", block=True),
    name="post",
)
class AskRAGView(APIView):
    """
    GET  /api/conversations/{id}/messages/ — Paginated retrieve of messages in a conversation.
    POST /api/conversations/{id}/messages/ — Core RAG endpoint.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        conversation = get_object_or_404(
            Conversation, pk=pk, user=request.user, is_deleted=False
        )
        # Prefetch retrieved_chunks to avoid N+1 queries
        messages = conversation.messages.prefetch_related("retrieved_chunks").order_by("created_at")
        
        paginator = CustomPagination()
        page = paginator.paginate_queryset(messages, request, view=self)
        if page is not None:
            serializer = MessageSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)

    def post(self, request, pk):
        t_total_start = time.time()
        serializer = SendMessageSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("SendMessageSerializer validation failed: Errors=%s, RequestData=%s", serializer.errors, request.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        content = serializer.validated_data["content"]

        try:
            # 1. Initialize RAG pipeline
            pipeline = RAGPipeline()
            pipeline.initialize()
        except Exception as e:
            logger.error("RAG Pipeline initialization failed: %s", e, exc_info=True)
            return Response(
                {"error": "ML stack models are currently unavailable. Please verify model files are on disk."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        with transaction.atomic():
            # 2. Resolve conversation session (it must exist already, created by POST /api/conversations/)
            conversation = get_object_or_404(
                Conversation, pk=pk, user=request.user, is_deleted=False
            )
            
            # Determine if this is the first user message in this conversation
            is_new = not conversation.messages.filter(role="user").exists()

            # 3. Persist the User Message
            user_message = Message.objects.create(
                conversation=conversation,
                role="user",
                content=content,
                tokens_estimate=len(content) // 4,
            )

            # 4. Perform Retrieval (Dense FAISS + local BM25 Reranking)
            try:
                retrieved_chunks, retrieve_timings = pipeline.retrieve(
                    query=content, k=settings.RAG_DEFAULT_K
                )
            except Exception as e:
                logger.error("Retrieval failed: %s", e, exc_info=True)
                return Response(
                    {"error": "Context retrieval failed. The vector index might be unavailable."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # 5. Execute LLM Generation (Local Qwen2.5 GGUF via llama-cpp)
            try:
                answer, gen_time = pipeline.generate(content, retrieved_chunks)
            except Exception as e:
                logger.error("LLM Generation failed: %s", e, exc_info=True)
                return Response(
                    {"error": "Local generation failed. The Qwen model engine encountered an error."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # 6. Save Assistant Reply
            total_time = time.time() - t_total_start
            generation_info = {
                "timings": {
                    "embed_time": round(retrieve_timings["embed_time"], 3),
                    "qdrant_time": round(retrieve_timings["qdrant_time"], 3),
                    "gen_time": round(gen_time, 3),
                    "total_time": round(total_time, 3),
                }
            }

            assistant_message = Message.objects.create(
                conversation=conversation,
                role="assistant",
                content=answer,
                tokens_estimate=len(answer) // 4,
                generation_info=generation_info,
            )

            # 7. Persist retrieved source chunks
            for chunk in retrieved_chunks:
                RetrievedChunk.objects.create(
                    message=assistant_message,
                    titre=chunk["titre"],
                    texte=chunk["texte"],
                    source_file=chunk["source_file"],
                    score=chunk["score"],
                    raw_meta=chunk["raw_meta"],
                )

            # 8. Auto-generate a descriptive title for first-time session
            if is_new:
                title = generate_conversation_title(content)
                conversation.title = title
                
            conversation.updated_at = timezone.now()
            conversation.save()

        # Log performance metrics in performance logger
        perf_logger = logging.getLogger("rag_pipeline")
        perf_logger.info(
            "Query execution: User=%s, Conv=%s, TotalTime=%.3fs, GenTime=%.3fs",
            request.user.email, conversation.id, total_time, gen_time
        )

        return Response(
            {
                "user_message": MessageSerializer(user_message).data,
                "assistant_message": MessageSerializer(assistant_message).data,
                "conversation": {
                    "id": str(conversation.id),
                    "title": conversation.title,
                    "created_at": conversation.created_at.isoformat(),
                    "updated_at": conversation.updated_at.isoformat(),
                },
                "timings": generation_info["timings"],
            },
            status=status.HTTP_201_CREATED,
        )


# ─── 2. GET/POST /api/conversations/ ─────────────────────────────────────────

class ConversationListView(generics.ListCreateAPIView):
    """
    GET  /api/conversations/ — Flat list of active conversations (no pagination).
    POST /api/conversations/ — Create a new conversation session.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Frontend expects a flat JSON array

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ConversationDetailSerializer
        return ConversationListSerializer

    def get_queryset(self):
        from django.db.models import Count
        return (
            Conversation.objects.filter(user=self.request.user, is_deleted=False)
            .annotate(message_count_annotated=Count("messages"))
            .order_by("-updated_at")
        )

    def create(self, request, *args, **kwargs):
        conversation = Conversation.objects.create(
            user=request.user,
            title="New Conversation"
        )
        logger.info("New conversation session created: %s", conversation.id)
        serializer = self.get_serializer(conversation)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ─── 5. POST /api/chat/conversations/{id}/messages/create/ ────────────────────

class MessageCreateView(APIView):
    """
    POST /api/chat/conversations/{id}/messages/create/
    Manually create a message in a conversation (developer seed / custom text entry).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        conversation = get_object_or_404(
            Conversation, pk=pk, user=request.user, is_deleted=False
        )
        role = request.data.get("role", "user")
        content = request.data.get("content", "").strip()

        if role not in ["user", "assistant", "system"]:
            return Response(
                {"error": "Role must be 'user', 'assistant', or 'system'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not content:
            return Response(
                {"error": "Content is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        message = Message.objects.create(
            conversation=conversation,
            role=role,
            content=content,
            tokens_estimate=len(content) // 4,
        )
        
        conversation.updated_at = timezone.now()
        conversation.save()

        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)


# ─── 6. DELETE /api/chat/conversations/cleanup/ ──────────────────────────────

class CleanupConversationsView(APIView):
    """
    DELETE /api/chat/conversations/cleanup/
    Soft-deletes empty conversations or stale conversations older than 5 minutes.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        cutoff_time = timezone.now() - timedelta(minutes=5)
        
        # Soft delete empty conversations (0 messages)
        empty_convs = Conversation.objects.filter(
            user=request.user,
            is_deleted=False,
            messages__isnull=True,
            created_at__lt=cutoff_time
        )
        
        count_empty = empty_convs.count()
        empty_convs.update(is_deleted=True, metadata={"deleted_reason": "cleanup_empty"})
        
        logger.info("Cleanup: Soft deleted %d empty conversations for user %s", count_empty, request.user.email)
        
        return Response(
            {
                "message": "Cleanup completed successfully.",
                "deleted_empty_count": count_empty,
            },
            status=status.HTTP_200_OK
        )


# ─── 7. POST /api/chat/conversations/{id}/generate-title/ ────────────────────

class GenerateTitleView(APIView):
    """
    POST /api/chat/conversations/{id}/generate-title/
    Manually triggers generation of a clean, short title using local LLM based on conversation.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        conversation = get_object_or_404(
            Conversation, pk=pk, user=request.user, is_deleted=False
        )
        first_message = conversation.messages.filter(role="user").first()
        if not first_message:
            return Response(
                {"error": "No user message found in this conversation to generate a title from."},
                status=status.HTTP_400_BAD_REQUEST
            )

        title = generate_conversation_title(first_message.content)
        conversation.title = title
        conversation.save()

        return Response(
            {
                "message": "Title generated successfully.",
                "title": conversation.title,
            },
            status=status.HTTP_200_OK
        )


class ConversationDetailView(APIView):
    """
    GET    /api/chat/conversations/{id}/  — Get detailed conversation properties
    PATCH  /api/chat/conversations/{id}/  — Rename conversation manually
    DELETE /api/chat/conversations/{id}/  — Soft delete conversation manually
    """
    permission_classes = [IsAuthenticated]

    def _get_conversation(self, pk, user):
        return get_object_or_404(Conversation, pk=pk, user=user, is_deleted=False)

    def get(self, request, pk):
        conversation = self._get_conversation(pk, request.user)
        serializer = ConversationDetailSerializer(conversation)
        return Response(serializer.data)

    def patch(self, request, pk):
        conversation = self._get_conversation(pk, request.user)
        serializer = RenameConversationSerializer(conversation, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        conversation = get_object_or_404(Conversation, pk=pk, user=request.user, is_deleted=False)
        conversation.is_deleted = True
        conversation.metadata["deleted_reason"] = "user_deleted"
        conversation.save()
        logger.info("Conversation %s soft-deleted by user %s", pk, request.user.email)
        return Response(status=status.HTTP_204_NO_CONTENT)
