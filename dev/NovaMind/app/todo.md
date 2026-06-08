# NovaMind AI Chat Application

## Design References
- ChatGPT-style conversational UI with unique visual identity
- Modern glassmorphism + gradient aesthetics
- Clean, minimal UX with bold accent colors

## Color Palette
- `#241E20` - Dark charcoal (dark mode backgrounds, sidebar)
- `#0083C9` - Vivid blue (primary accent, buttons, links, active states)
- `#F7941D` - Warm orange (secondary accent, highlights, CTAs, notifications)
- `#F3F3F3` - Light gray (light mode backgrounds)
- Supporting: white, near-black, muted grays for text/borders

## Typography
- Inter (system font stack) for body text
- Bold weights for headings, medium for UI labels
- Monospace for code blocks in chat

## Key Component Styles
- Rounded cards with subtle shadows
- Glassmorphism sidebar with backdrop blur
- Smooth 200ms transitions on theme toggle
- Animated gradient accents on landing page
- Chat bubbles: user = blue bg, assistant = muted bg with left border accent

## Images to Generate
1. `hero-ai-chat-concept.jpg` - Landing page hero banner, futuristic AI chat interface concept
2. `logo-novamind-icon.png` - App logo icon, minimalist brain/spark mark, transparent bg

## Development Tasks
- [x] Update `src/index.css` with custom theme variables using color palette (#241E20, #0083C9, #F7941D, #F3F3F3) for both light and dark modes
- [x] Create `src/lib/store.ts` with Zustand store for auth state, conversations, messages, theme, and mock data
- [x] Create `src/components/ChatUI.tsx` with all chat components (Sidebar, ChatBubble, ChatInput, TypingIndicator, ConversationList)
- [x] Create `src/pages/Index.tsx` as animated landing page with hero section, features, and CTAs
- [x] Create `src/pages/Auth.tsx` with Sign In and Sign Up forms
- [x] Create `src/pages/Chat.tsx` as main chat interface page
- [x] Update `src/App.tsx` with router, layout wrapper, theme toggle, and all routes
- [x] Install Zustand dependency and run lint/build checks