import { create } from "zustand";
import { persist } from "zustand/middleware";
import { authAPI, chatAPI, tokenStorage } from "./apiClient";
import type { AxiosError } from "axios";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
}

export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string | null;
}

// ─── Helper ──────────────────────────────────────────────────────────────────

function extractError(err: unknown): string {
  const axiosErr = err as AxiosError<Record<string, unknown>>;
  const data = axiosErr?.response?.data;
  if (!data) return "Something went wrong. Please try again.";

  // Simple top-level error/detail string
  if (typeof data === "string") return data;
  if (typeof data.error === "string") return data.error;
  if (typeof data.detail === "string") return data.detail;

  // DRF validation errors: { field: ["msg", ...], ... }
  // or { non_field_errors: ["msg"] }
  const messages: string[] = [];
  for (const [key, value] of Object.entries(data)) {
    if (Array.isArray(value)) {
      const fieldLabel = key === "non_field_errors" ? "" : `${key}: `;
      messages.push(...value.map((v) => `${fieldLabel}${v}`));
    } else if (typeof value === "string") {
      messages.push(value);
    }
  }
  return messages.length > 0
    ? messages.join(" ")
    : "Something went wrong. Please try again.";
}

/** Convert a back-end message object to front-end Message shape */
function toMessage(m: {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}): Message {
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    timestamp: new Date(m.timestamp).getTime(),
  };
}

/** Convert back-end conversation to front-end Conversation shape */
function toConversation(c: {
  id: string;
  title: string;
  messages?: Array<{ id: string; role: "user" | "assistant"; content: string; timestamp: string }>;
  created_at: string;
  updated_at: string;
}): Conversation {
  return {
    id: c.id,
    title: c.title,
    messages: (c.messages ?? []).map(toMessage),
    createdAt: new Date(c.created_at).getTime(),
    updatedAt: new Date(c.updated_at).getTime(),
  };
}

// ─── Store Interface ─────────────────────────────────────────────────────────

interface AppState {
  // Theme
  theme: "light" | "dark";
  toggleTheme: () => void;

  // Auth
  isAuthenticated: boolean;
  user: User | null;
  authLoading: boolean;
  authError: string | null;
  signIn: (email: string, password: string) => Promise<boolean>;
  signUp: (name: string, email: string, password: string) => Promise<boolean>;
  signOut: () => Promise<void>;
  loadProfile: () => Promise<void>;

  // Conversations
  conversations: Conversation[];
  activeConversationId: string | null;
  conversationsLoading: boolean;
  setActiveConversation: (id: string | null) => void;
  loadConversations: () => Promise<void>;
  loadConversationMessages: (id: string) => Promise<void>;
  createConversation: () => Promise<string>;
  deleteConversation: (id: string) => Promise<void>;
  renameConversation: (id: string, title: string) => Promise<void>;

  // Messages
  isTyping: boolean;
  sendMessage: (conversationId: string, content: string) => Promise<void>;

  // Sidebar
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
}

// ─── Store ───────────────────────────────────────────────────────────────────

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // ── Theme ──────────────────────────────────────────────────────────────
      theme: "dark",
      toggleTheme: () =>
        set((state) => {
          const newTheme = state.theme === "light" ? "dark" : "light";
          if (newTheme === "dark") {
            document.documentElement.classList.add("dark");
          } else {
            document.documentElement.classList.remove("dark");
          }
          return { theme: newTheme };
        }),

      // ── Auth ───────────────────────────────────────────────────────────────
      isAuthenticated: false,
      user: null,
      authLoading: false,
      authError: null,

      signIn: async (email, password) => {
        set({ authLoading: true, authError: null });
        try {
          const res = await authAPI.login({ email, password });
          const { user, tokens } = res.data;
          tokenStorage.setTokens(tokens.access, tokens.refresh);
          set({
            isAuthenticated: true,
            user: {
              id: user.id,
              name: user.name,
              email: user.email,
              avatar: user.avatar_url,
            },
            authLoading: false,
          });
          // Load conversations right after sign-in
          await get().loadConversations();
          return true;
        } catch (err) {
          set({ authError: extractError(err), authLoading: false });
          return false;
        }
      },

      signUp: async (name, email, password) => {
        set({ authLoading: true, authError: null });
        try {
          const res = await authAPI.register({
            name,
            email,
            password,
            confirm_password: password,
          });
          const { user, tokens } = res.data;
          tokenStorage.setTokens(tokens.access, tokens.refresh);
          set({
            isAuthenticated: true,
            user: {
              id: user.id,
              name: user.name,
              email: user.email,
              avatar: user.avatar_url,
            },
            authLoading: false,
            conversations: [],
          });
          return true;
        } catch (err) {
          set({ authError: extractError(err), authLoading: false });
          return false;
        }
      },

      signOut: async () => {
        const refresh = tokenStorage.getRefresh();
        if (refresh) {
          try {
            await authAPI.logout(refresh);
          } catch {
            // ignore — clear tokens regardless
          }
        }
        tokenStorage.clearTokens();
        set({
          isAuthenticated: false,
          user: null,
          conversations: [],
          activeConversationId: null,
        });
      },

      loadProfile: async () => {
        try {
          const res = await authAPI.getProfile();
          const u = res.data;
          set({
            user: { id: u.id, name: u.name, email: u.email, avatar: u.avatar_url },
          });
        } catch {
          // Token may be invalid — sign out
          get().signOut();
        }
      },

      // ── Conversations ──────────────────────────────────────────────────────
      conversations: [],
      activeConversationId: null,
      conversationsLoading: false,

      setActiveConversation: (id) => set({ activeConversationId: id }),

      loadConversations: async () => {
        set({ conversationsLoading: true });
        try {
          const res = await chatAPI.listConversations();
          const conversations: Conversation[] = res.data.map(
            (c: Parameters<typeof toConversation>[0]) => toConversation(c)
          );
          set({ conversations, conversationsLoading: false });
        } catch {
          set({ conversationsLoading: false });
        }
      },

      loadConversationMessages: async (id) => {
        try {
          const res = await chatAPI.getConversation(id);
          const updated = toConversation(res.data);
          set((state) => ({
            conversations: state.conversations.map((c) =>
              c.id === id ? updated : c
            ),
          }));
        } catch {
          // silently fail — messages already shown from local state
        }
      },

      createConversation: async () => {
        try {
          const res = await chatAPI.createConversation();
          const newConv = toConversation(res.data);
          set((state) => ({
            conversations: [newConv, ...state.conversations],
            activeConversationId: newConv.id,
          }));
          return newConv.id;
        } catch {
          // Optimistic fallback with a temp ID
          const tempId = `temp-${Date.now()}`;
          const tempConv: Conversation = {
            id: tempId,
            title: "New Conversation",
            messages: [],
            createdAt: Date.now(),
            updatedAt: Date.now(),
          };
          set((state) => ({
            conversations: [tempConv, ...state.conversations],
            activeConversationId: tempId,
          }));
          return tempId;
        }
      },

      deleteConversation: async (id) => {
        // Optimistic remove
        set((state) => ({
          conversations: state.conversations.filter((c) => c.id !== id),
          activeConversationId:
            state.activeConversationId === id ? null : state.activeConversationId,
        }));
        try {
          await chatAPI.deleteConversation(id);
        } catch {
          // Refresh to restore if failed
          get().loadConversations();
        }
      },

      renameConversation: async (id, title) => {
        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === id ? { ...c, title } : c
          ),
        }));
        try {
          await chatAPI.renameConversation(id, title);
        } catch {
          // Silently fail — optimistic update stays
        }
      },

      // ── Messages ───────────────────────────────────────────────────────────
      isTyping: false,

      sendMessage: async (conversationId, content) => {
        // 1. Optimistically show user message
        const tempUserMsg: Message = {
          id: `temp-user-${Date.now()}`,
          role: "user",
          content,
          timestamp: Date.now(),
        };
        set((state) => ({
          isTyping: true,
          conversations: state.conversations.map((c) =>
            c.id === conversationId
              ? { ...c, messages: [...c.messages, tempUserMsg], updatedAt: Date.now() }
              : c
          ),
        }));

        try {
          const res = await chatAPI.sendMessage(conversationId, content);
          const { user_message, assistant_message, conversation: updatedConv } = res.data;

          set((state) => ({
            isTyping: false,
            conversations: state.conversations.map((c) => {
              if (c.id !== conversationId) return c;
              // Replace temp user message with real one + add assistant reply
              const withoutTemp = c.messages.filter((m) => m.id !== tempUserMsg.id);
              return {
                ...c,
                title: updatedConv.title,
                messages: [
                  ...withoutTemp,
                  toMessage(user_message),
                  toMessage(assistant_message),
                ],
                updatedAt: new Date(updatedConv.updated_at).getTime(),
              };
            }),
          }));
        } catch (err) {
          // Remove temp message on error
          set((state) => ({
            isTyping: false,
            conversations: state.conversations.map((c) =>
              c.id === conversationId
                ? { ...c, messages: c.messages.filter((m) => m.id !== tempUserMsg.id) }
                : c
            ),
          }));
          throw err;
        }
      },

      // ── Sidebar ────────────────────────────────────────────────────────────
      sidebarOpen: true,
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
    }),
    {
      name: "novamind-storage",
      partialize: (state) => ({
        theme: state.theme,
        isAuthenticated: state.isAuthenticated,
        user: state.user,
        activeConversationId: state.activeConversationId,
        // Don't persist conversations — always fetch fresh from API
      }),
      onRehydrateStorage: () => (state) => {
        if (state?.theme === "dark") {
          document.documentElement.classList.add("dark");
        }
        // If we have persisted auth state, validate that tokens still exist
        if (state?.isAuthenticated) {
          const token = tokenStorage.getAccess();
          if (!token) {
            // Tokens were cleared (expired / logout) — reset auth state
            tokenStorage.clearTokens();
            state.isAuthenticated = false;
            state.user = null;
            state.conversations = [];
            state.activeConversationId = null;
          } else {
            // Token exists — try to load conversations (will auto-refresh if needed)
            setTimeout(() => {
              state.loadConversations();
            }, 100);
          }
        }
      },
    }
  )
);