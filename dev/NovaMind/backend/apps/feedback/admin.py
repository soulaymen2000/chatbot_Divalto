"""Admin registration for the feedback app."""
from django.contrib import admin
from django.db.models import Avg
from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "sentiment",
        "rating",
        "issue_type",
        "short_comment",
        "timestamp",
    )
    list_filter = ("sentiment", "rating", "issue_type", "timestamp")
    search_fields = ("user__email", "comment", "conversation__title")
    readonly_fields = ("id", "user", "message", "conversation", "timestamp")
    ordering = ("-timestamp",)

    def short_comment(self, obj):
        return obj.comment[:60] + ("..." if len(obj.comment) > 60 else "")
    short_comment.short_description = "Comment"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        qs = self.get_queryset(request)
        extra_context["avg_rating"] = qs.aggregate(avg=Avg("rating"))["avg"] or 0
        extra_context["total"] = qs.count()
        return super().changelist_view(request, extra_context=extra_context)
