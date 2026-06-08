import { useEffect, useRef, useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAppStore } from "@/lib/store";
import {
  Sidebar,
  ChatHeader,
  ChatBubble,
  ChatInput,
  TypingIndicator,
  EmptyChatState,
} from "@/components/ChatUI";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useToast } from "@/hooks/use-toast";

export default function ChatPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const {
    isAuthenticated,
    conversations,
    activeConversationId,
    isTyping,
    sidebarOpen,
    toggleSidebar,
    setSidebarOpen,
    sendMessage,
    createConversation,
    loadConversationMessages,
  } = useAppStore();

  const scrollRef = useRef<HTMLDivElement>(null);
  const [sendError, setSendError] = useState<string | null>(null);

  // Redirect if not authenticated
  useEffect(() => {
    if (!isAuthenticated) {
      navigate("/auth");
    }
  }, [isAuthenticated, navigate]);

  // Load full messages when switching conversations
  useEffect(() => {
    if (activeConversationId) {
      const conv = conversations.find((c) => c.id === activeConversationId);
      // Only fetch if messages haven't been loaded yet (empty or stale)
      if (conv && conv.messages.length === 0) {
        loadConversationMessages(activeConversationId);
      }
    }
  }, [activeConversationId]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [conversations, isTyping]);

  // Responsive sidebar
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 768) {
        setSidebarOpen(false);
      }
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [setSidebarOpen]);

  const activeConversation = conversations.find(
    (c) => c.id === activeConversationId
  );

  const handleSendMessage = useCallback(
    async (content: string) => {
      setSendError(null);
      let convId = activeConversationId;

      // Create a new conversation if none is active
      if (!convId) {
        try {
          convId = await createConversation();
        } catch {
          toast({
            title: "Error",
            description: "Could not create a conversation. Please try again.",
            variant: "destructive",
          });
          return;
        }
      }

      try {
        await sendMessage(convId, content);
      } catch {
        setSendError("Failed to get a response. Please try again.");
        toast({
          title: "AI Error",
          description: "The AI service is unavailable. Check your Gemini API key.",
          variant: "destructive",
        });
      }
    },
    [activeConversationId, createConversation, sendMessage, toast]
  );

  if (!isAuthenticated) return null;

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* Main Chat Area */}
      <div className="flex flex-1 flex-col min-w-0">
        <ChatHeader
          onToggleSidebar={toggleSidebar}
          sidebarOpen={sidebarOpen}
        />

        {activeConversation && activeConversation.messages.length > 0 ? (
          <>
            {/* Messages Area */}
            <ScrollArea className="flex-1">
              <div
                ref={scrollRef}
                className="mx-auto max-w-3xl space-y-6 px-4 py-6"
              >
                {activeConversation.messages.map((message, index) => (
                  <ChatBubble
                    key={message.id}
                    role={message.role}
                    content={message.content}
                    messageId={message.id}
                    index={index}
                  />
                ))}
                {isTyping && <TypingIndicator />}

                {sendError && (
                  <div className="rounded-xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive text-center animate-fade-in">
                    {sendError}
                  </div>
                )}
              </div>
            </ScrollArea>

            {/* Input Area */}
            <ChatInput
              onSend={handleSendMessage}
              disabled={isTyping}
            />
          </>
        ) : (
          <EmptyChatState onSend={handleSendMessage} />
        )}
      </div>
    </div>
  );
}