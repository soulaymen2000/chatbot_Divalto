import { useState, useRef, useEffect, useCallback } from "react";
import { useAppStore } from "@/lib/store";
import { feedbackAPI } from "@/lib/apiClient";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Plus,
  MessageSquare,
  Trash2,
  Send,
  Menu,
  X,
  Sparkles,
  Sun,
  Moon,
  LogOut,
  ChevronDown,
  ThumbsUp,
  ThumbsDown,
  Star,
  RotateCcw,
  Pencil,
  Check,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

// ─── Theme Toggle ────────────────────────────────────────────────────────────

export function ThemeToggle() {
  const { theme, toggleTheme } = useAppStore();

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggleTheme}
      className="relative h-9 w-9 rounded-full hover:bg-accent"
      aria-label="Toggle theme"
    >
      <Sun className={`h-4 w-4 transition-all ${theme === "dark" ? "scale-0 rotate-90" : "scale-100 rotate-0"}`} />
      <Moon className={`absolute h-4 w-4 transition-all ${theme === "dark" ? "scale-100 rotate-0" : "scale-0 -rotate-90"}`} />
    </Button>
  );
}

// ─── Typing Indicator ────────────────────────────────────────────────────────

export function TypingIndicator() {
  return (
    <div className="flex items-start gap-3 animate-message-appear">
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback className="bg-primary/10 text-primary text-xs">
          <Sparkles className="h-4 w-4" />
        </AvatarFallback>
      </Avatar>
      <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm bg-muted px-4 py-3">
        <span className="h-2 w-2 rounded-full bg-primary/60 animate-bounce-dot" style={{ animationDelay: "0ms" }} />
        <span className="h-2 w-2 rounded-full bg-primary/60 animate-bounce-dot" style={{ animationDelay: "150ms" }} />
        <span className="h-2 w-2 rounded-full bg-primary/60 animate-bounce-dot" style={{ animationDelay: "300ms" }} />
      </div>
    </div>
  );
}

// ─── Feedback Bar ─────────────────────────────────────────────────────────────

interface FeedbackBarProps {
  messageId: string;
}

function FeedbackBar({ messageId }: FeedbackBarProps) {
  const [sentiment, setSentiment] = useState<"helpful" | "not_helpful" | null>(null);
  const [rating, setRating] = useState<number>(0);
  const [hoverRating, setHoverRating] = useState<number>(0);
  const [submitted, setSubmitted] = useState(false);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState("");

  const submitFeedback = async (
    newSentiment?: "helpful" | "not_helpful",
    newRating?: number,
    newComment?: string
  ) => {
    const s = newSentiment ?? sentiment;
    const r = newRating ?? rating;
    const c = newComment ?? comment;
    if (!s && !r) return;
    try {
      await feedbackAPI.submitFeedback(messageId, {
        sentiment: s ?? undefined,
        rating: r || undefined,
        comment: c,
      });
      setSubmitted(true);
    } catch {
      // Silently fail — don't interrupt the user experience
    }
  };

  const handleSentiment = async (value: "helpful" | "not_helpful") => {
    if (submitted) return;
    setSentiment(value);
    await submitFeedback(value, rating, comment);
  };

  const handleStar = async (value: number) => {
    if (submitted) return;
    setRating(value);
    await submitFeedback(sentiment ?? undefined, value, comment);
  };

  const handleCommentSubmit = async () => {
    await submitFeedback(sentiment ?? undefined, rating, comment);
    setShowComment(false);
  };

  if (submitted && !showComment) {
    return (
      <div className="flex items-center gap-1.5 mt-2 text-xs text-muted-foreground">
        <Check className="h-3 w-3 text-green-500" />
        <span>Feedback recorded</span>
      </div>
    );
  }

  return (
    <div className="mt-2 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        {/* Thumbs */}
        <button
          onClick={() => handleSentiment("helpful")}
          title="Helpful"
          className={`rounded-md p-1.5 transition-all hover:bg-accent ${
            sentiment === "helpful" ? "text-green-500 bg-green-500/10" : "text-muted-foreground"
          }`}
        >
          <ThumbsUp className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={() => handleSentiment("not_helpful")}
          title="Not helpful"
          className={`rounded-md p-1.5 transition-all hover:bg-accent ${
            sentiment === "not_helpful" ? "text-destructive bg-destructive/10" : "text-muted-foreground"
          }`}
        >
          <ThumbsDown className="h-3.5 w-3.5" />
        </button>

        {/* Star rating */}
        <div className="flex items-center gap-0.5 ml-1">
          {[1, 2, 3, 4, 5].map((star) => (
            <button
              key={star}
              onMouseEnter={() => setHoverRating(star)}
              onMouseLeave={() => setHoverRating(0)}
              onClick={() => handleStar(star)}
              className="transition-transform hover:scale-110"
              title={`${star} star${star > 1 ? "s" : ""}`}
            >
              <Star
                className={`h-3.5 w-3.5 ${
                  star <= (hoverRating || rating)
                    ? "fill-yellow-400 text-yellow-400"
                    : "text-muted-foreground/40"
                }`}
              />
            </button>
          ))}
        </div>

        {/* Comment toggle */}
        {!showComment && (
          <button
            onClick={() => setShowComment(true)}
            className="ml-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Add comment
          </button>
        )}
      </div>

      {/* Optional comment */}
      {showComment && (
        <div className="flex items-center gap-2 animate-fade-in">
          <Input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What could be improved?"
            className="h-8 text-xs rounded-lg flex-1"
            onKeyDown={(e) => e.key === "Enter" && handleCommentSubmit()}
          />
          <Button size="sm" className="h-8 px-3 text-xs rounded-lg" onClick={handleCommentSubmit}>
            Send
          </Button>
          <button onClick={() => setShowComment(false)} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Chat Bubble ─────────────────────────────────────────────────────────────

interface ChatBubbleProps {
  role: "user" | "assistant";
  content: string;
  messageId: string;
  index: number;
}

export function ChatBubble({ role, content, messageId, index }: ChatBubbleProps) {
  const isUser = role === "user";

  return (
    <div
      className={`flex items-start gap-3 animate-message-appear ${isUser ? "flex-row-reverse" : ""}`}
      style={{ animationDelay: `${index * 50}ms` }}
    >
      <Avatar className={`h-8 w-8 shrink-0 ${isUser ? "ml-3" : "mr-3"}`}>
        <AvatarFallback
          className={`text-xs font-medium ${
            isUser ? "bg-secondary text-white" : "bg-primary/10 text-primary"
          }`}
        >
          {isUser ? "U" : <Sparkles className="h-4 w-4" />}
        </AvatarFallback>
      </Avatar>

      <div className={`flex flex-col ${isUser ? "items-end" : "items-start"} max-w-[75%]`}>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? "bg-primary text-primary-foreground rounded-tr-sm"
              : "bg-muted text-foreground rounded-tl-sm border-l-2 border-primary/30"
          }`}
        >
          <div className="markdown-content whitespace-pre-wrap">{content}</div>
        </div>

        {/* Feedback bar — only for assistant messages */}
        {!isUser && (
          <FeedbackBar messageId={messageId} />
        )}
      </div>
    </div>
  );
}

// ─── Auto-Resize Textarea ────────────────────────────────────────────────────

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [value, adjustHeight]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t bg-card/80 backdrop-blur-sm p-4">
      <div className="mx-auto flex max-w-3xl items-end gap-3">
        <div className="relative flex-1">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your message..."
            disabled={disabled}
            rows={1}
            className="flex min-h-[44px] w-full resize-none rounded-xl border border-input bg-background px-4 py-3 pr-12 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 custom-scrollbar"
          />
          <Button
            size="icon"
            onClick={handleSend}
            disabled={!value.trim() || disabled}
            className="absolute bottom-1.5 right-1.5 h-8 w-8 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <p className="mx-auto mt-2 max-w-3xl text-center text-xs text-muted-foreground">
        Infolib Assistant. Press <kbd className="rounded border px-1 py-0.5 text-[10px] font-mono">Enter</kbd> to send, <kbd className="rounded border px-1 py-0.5 text-[10px] font-mono">Shift+Enter</kbd> for new line.
      </p>
    </div>
  );
}

// ─── Conversation List Item ──────────────────────────────────────────────────

interface ConversationItemProps {
  id: string;
  title: string;
  isActive: boolean;
  onClick: () => void;
  onDelete: () => void;
  onRename: (title: string) => void;
}

function ConversationItem({ id, title, isActive, onClick, onDelete, onRename }: ConversationItemProps) {
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(title);

  const commitRename = () => {
    const trimmed = editTitle.trim();
    if (trimmed && trimmed !== title) {
      onRename(trimmed);
    }
    setEditing(false);
  };

  if (editing) {
    return (
      <div className="flex items-center gap-2 rounded-lg px-3 py-2 bg-primary/10">
        <Input
          autoFocus
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          onBlur={commitRename}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitRename();
            if (e.key === "Escape") setEditing(false);
          }}
          className="h-7 text-sm px-2 rounded-md"
        />
        <button onClick={commitRename} className="text-primary">
          <Check className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div
      onClick={onClick}
      className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 cursor-pointer transition-all duration-150 ${
        isActive
          ? "bg-primary/10 text-primary font-medium"
          : "text-foreground/70 hover:bg-accent hover:text-foreground"
      }`}
    >
      <MessageSquare className="h-4 w-4 shrink-0" />
      <span className="flex-1 truncate text-sm">{title}</span>
      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
        <Button
          variant="ghost"
          size="icon"
          onClick={(e) => {
            e.stopPropagation();
            setEditing(true);
            setEditTitle(title);
          }}
          className="h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground"
        >
          <Pencil className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const {
    conversations,
    activeConversationId,
    setActiveConversation,
    createConversation,
    deleteConversation,
    renameConversation,
    user,
    signOut,
    conversationsLoading,
  } = useAppStore();

  const handleNewChat = async () => {
    await createConversation();
    if (window.innerWidth < 768) onClose();
  };

  const handleSelectConversation = (id: string) => {
    setActiveConversation(id);
    if (window.innerWidth < 768) onClose();
  };

  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-sidebar-border bg-sidebar-background transition-transform duration-300 ease-in-out md:relative md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Sidebar Header */}
        <div className="flex items-center justify-between p-4 border-b border-sidebar-border">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Sparkles className="h-4 w-4" />
            </div>
            <span className="font-semibold text-sm">Infolib</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 md:hidden"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* New Chat Button */}
        <div className="p-3">
          <Button
            onClick={handleNewChat}
            className="w-full justify-start gap-2 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 font-medium"
            variant="ghost"
          >
            <Plus className="h-4 w-4" />
            New Chat
          </Button>
        </div>

        {/* Conversation List */}
        <ScrollArea className="flex-1 px-3">
          <div className="space-y-1 pb-4">
            {conversationsLoading ? (
              <div className="flex justify-center py-8">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              </div>
            ) : conversations.length === 0 ? (
              <p className="px-3 py-8 text-center text-sm text-muted-foreground">
                No conversations yet.
                <br />
                Start a new chat!
              </p>
            ) : (
              conversations.map((conv) => (
                <ConversationItem
                  key={conv.id}
                  id={conv.id}
                  title={conv.title}
                  isActive={activeConversationId === conv.id}
                  onClick={() => handleSelectConversation(conv.id)}
                  onDelete={() => deleteConversation(conv.id)}
                  onRename={(title) => renameConversation(conv.id, title)}
                />
              ))
            )}
          </div>
        </ScrollArea>

        {/* Sidebar Footer */}
        <div className="border-t border-sidebar-border p-3">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="w-full justify-start gap-3 rounded-lg px-3 py-2.5"
              >
                <Avatar className="h-7 w-7">
                  <AvatarFallback className="bg-secondary text-white text-xs">
                    {user?.name?.charAt(0) || "U"}
                  </AvatarFallback>
                </Avatar>
                <span className="flex-1 text-left text-sm truncate">
                  {user?.name || "User"}
                </span>
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuItem
                onClick={() => signOut()}
                className="text-destructive focus:text-destructive"
              >
                <LogOut className="mr-2 h-4 w-4" />
                Sign Out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </aside>
    </>
  );
}

// ─── Chat Header ─────────────────────────────────────────────────────────────

interface ChatHeaderProps {
  onToggleSidebar: () => void;
  sidebarOpen: boolean;
}

export function ChatHeader({ onToggleSidebar, sidebarOpen }: ChatHeaderProps) {
  const { activeConversationId, conversations } = useAppStore();
  const activeConversation = conversations.find((c) => c.id === activeConversationId);

  return (
    <header className="flex items-center gap-3 border-b bg-card/80 backdrop-blur-sm px-4 py-3">
      <Button
        variant="ghost"
        size="icon"
        onClick={onToggleSidebar}
        className="h-9 w-9 shrink-0 md:hidden"
      >
        <Menu className="h-5 w-5" />
      </Button>
      <div className="flex-1 min-w-0">
        <h2 className="text-sm font-medium truncate">
          {activeConversation?.title || "Infolib"}
        </h2>
        <p className="text-xs text-muted-foreground">
          {activeConversation
            ? `${activeConversation.messages.length} messages`
            : "Your personal assistant"}
        </p>
      </div>
      <ThemeToggle />
    </header>
  );
}

// ─── Empty Chat State ────────────────────────────────────────────────────────

export function EmptyChatState({ onSend }: { onSend: (message: string) => void }) {
  const [quickInput, setQuickInput] = useState("");

  const suggestions = [
    "Explain quantum computing in simple terms",
    "Write a creative short story",
    "Help me debug my React code",
    "Suggest a healthy meal plan",
  ];

  return (
    <div className="flex flex-1 flex-col items-center justify-center p-8 animate-fade-in">
      <div className="mb-8 flex h-20 w-20 items-center justify-center rounded-2xl bg-primary/10 animate-pulse-glow">
        <Sparkles className="h-10 w-10 text-primary" />
      </div>
      <h2 className="mb-2 text-2xl font-bold">How can I help you today?</h2>
      <p className="mb-8 max-w-md text-center text-muted-foreground">
        I'm Infolib. Ask me anything — from coding questions to creative writing.
      </p>

      {/* Quick suggestions */}
      <div className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-2 max-w-2xl w-full">
        {suggestions.map((suggestion) => (
          <button
            key={suggestion}
            onClick={() => onSend(suggestion)}
            className="rounded-xl border border-border bg-card p-4 text-left text-sm transition-all hover:border-primary/50 hover:bg-accent hover:shadow-md group"
          >
            <span className="text-foreground/80 group-hover:text-foreground">{suggestion}</span>
          </button>
        ))}
      </div>

      {/* Quick input */}
      <div className="w-full max-w-xl">
        <div className="relative">
          <Input
            value={quickInput}
            onChange={(e) => setQuickInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && quickInput.trim()) {
                onSend(quickInput.trim());
                setQuickInput("");
              }
            }}
            placeholder="Or type your question here..."
            className="pr-12 rounded-xl h-12"
          />
          <Button
            size="icon"
            onClick={() => {
              if (quickInput.trim()) {
                onSend(quickInput.trim());
                setQuickInput("");
              }
            }}
            disabled={!quickInput.trim()}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 h-9 w-9 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}