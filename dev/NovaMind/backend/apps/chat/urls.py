"""URL patterns for the chat / RAG chatbot app."""
from django.urls import path
from .views import (
    AskRAGView,
    ConversationListView,
    ConversationDetailView,
    CleanupConversationsView,
    GenerateTitleView,
    MessageCreateView,
)

urlpatterns = [
    # GET /api/conversations/ (list) and POST /api/conversations/ (create)
    path("conversations/", ConversationListView.as_view(), name="conversation-list"),

    # DELETE /api/conversations/cleanup/ (soft delete empty/stale sessions)
    path("conversations/cleanup/", CleanupConversationsView.as_view(), name="conversation-cleanup"),

    # GET/PATCH/DELETE /api/conversations/<uuid:pk>/ (detail, rename, soft-delete)
    path("conversations/<uuid:pk>/", ConversationDetailView.as_view(), name="conversation-detail"),

    # GET /api/conversations/<uuid:pk>/messages/ (list messages)
    # POST /api/conversations/<uuid:pk>/messages/ (send message and run RAG pipeline)
    path("conversations/<uuid:pk>/messages/", AskRAGView.as_view(), name="conversation-messages"),

    # POST /api/conversations/<uuid:pk>/messages/create/ (developer seed / manual create)
    path("conversations/<uuid:pk>/messages/create/", MessageCreateView.as_view(), name="message-create"),

    # POST /api/conversations/<uuid:pk>/generate-title/ (explicit LLM title generator)
    path("conversations/<uuid:pk>/generate-title/", GenerateTitleView.as_view(), name="conversation-generate-title"),
]
