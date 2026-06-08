"""Admin registration for the chat app."""
from django.contrib import admin
from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("id", "role", "content", "tokens_estimate", "created_at")
    ordering = ("created_at",)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "message_count", "created_at", "updated_at")
    list_filter = ("created_at",)
    search_fields = ("title", "user__email", "user__name")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [MessageInline]

    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = "Messages"


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("short_content", "role", "conversation", "tokens_estimate", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("content", "conversation__title")
    readonly_fields = ("id", "created_at")

    def short_content(self, obj):
        return obj.content[:80] + ("..." if len(obj.content) > 80 else "")
    short_content.short_description = "Content"
