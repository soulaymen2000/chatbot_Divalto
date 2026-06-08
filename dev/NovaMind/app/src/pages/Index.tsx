import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAppStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ChatUI";
import {
  Sparkles,
  MessageSquare,
  Zap,
  Shield,
  ArrowRight,
  ChevronRight,
  Globe,
  Brain,
} from "lucide-react";

const HERO_IMAGE = "https://mgx-backend-cdn.metadl.com/generate/images/1156904/2026-04-26/nmkks5aaafnq/hero-ai-chat-concept.png";
const LOGO_IMAGE = "https://mgx-backend-cdn.metadl.com/generate/images/1156904/2026-04-26/nmkkosyaafmq/logo-novamind-icon.png";

export default function IndexPage() {
  const navigate = useNavigate();
  const { isAuthenticated } = useAppStore();
  const [scrollY, setScrollY] = useState(0);

  useEffect(() => {
    const handleScroll = () => setScrollY(window.scrollY);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const handleGetStarted = () => {
    if (isAuthenticated) {
      navigate("/chat");
    } else {
      navigate("/auth");
    }
  };

  return (
    <div className="min-h-screen bg-background overflow-hidden">
      {/* Navbar */}
      <nav
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
          scrollY > 50 ? "glass border-b shadow-sm" : "bg-transparent"
        }`}
      >
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2.5">
            <img src={LOGO_IMAGE} alt="Infolib AI" className="h-8 w-8 rounded-lg" />
            <span className="text-xl font-bold bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
              Infolib AI
            </span>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            {isAuthenticated ? (
              <Button onClick={() => navigate("/chat")} className="rounded-full gap-2">
                <MessageSquare className="h-4 w-4" />
                Open Chat
              </Button>
            ) : (
              <>
                <Button
                  variant="ghost"
                  onClick={() => navigate("/auth")}
                  className="hidden sm:flex rounded-full"
                >
                  Sign In
                </Button>
                <Button onClick={() => navigate("/auth")} className="rounded-full gap-2">
                  Get Started
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center hero-gradient">
        {/* Animated background orbs */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute -top-40 -right-40 h-96 w-96 rounded-full bg-primary/5 blur-3xl animate-float" />
          <div
            className="absolute -bottom-40 -left-40 h-96 w-96 rounded-full bg-secondary/5 blur-3xl animate-float"
            style={{ animationDelay: "3s" }}
          />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-[600px] w-[600px] rounded-full bg-primary/3 blur-3xl animate-spin-slow" />
        </div>

        <div className="relative z-10 mx-auto max-w-7xl px-6 py-32 text-center">
          {/* Badge */}
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-4 py-1.5 text-sm text-primary animate-fade-in-up">
            <Sparkles className="h-3.5 w-3.5" />
            Powered by Infolib
          </div>

          {/* Heading */}
          <h1 className="mb-6 text-5xl font-extrabold tracking-tight sm:text-6xl lg:text-7xl animate-fade-in-up" style={{ animationDelay: "0.1s" }}>
            Your Intelligent
            <br />
            <span className="bg-gradient-to-r from-primary via-primary to-secondary bg-clip-text text-transparent animate-gradient">
              Assistant
            </span>
          </h1>

          {/* Subtitle */}
          <p
            className="mx-auto mb-10 max-w-2xl text-lg text-muted-foreground sm:text-xl animate-fade-in-up"
            style={{ animationDelay: "0.2s" }}
          >
            Experience the next generation of conversation. Infolib understands context,
            generates creative content, and helps you accomplish more — all with a beautiful,
            intuitive interface.
          </p>

          {/* CTA Buttons */}
          <div
            className="flex flex-col sm:flex-row items-center justify-center gap-4 animate-fade-in-up"
            style={{ animationDelay: "0.3s" }}
          >
            <Button
              size="lg"
              onClick={handleGetStarted}
              className="rounded-full px-8 py-6 text-base font-semibold gap-2 shadow-lg shadow-primary/25 hover:shadow-xl hover:shadow-primary/30 transition-all"
            >
              Start Chatting Free
              <ArrowRight className="h-5 w-5" />
            </Button>
            <Button
              size="lg"
              variant="outline"
              onClick={handleGetStarted}
              className="rounded-full px-8 py-6 text-base font-semibold gap-2"
            >
              See How It Works
              <ChevronRight className="h-5 w-5" />
            </Button>
          </div>

          {/* Hero Image */}
          <div
            className="mt-16 mx-auto max-w-4xl animate-fade-in-up"
            style={{ animationDelay: "0.5s" }}
          >
            <div className="relative rounded-2xl border border-border/50 bg-card/50 p-2 shadow-2xl backdrop-blur-sm">
              <div className="rounded-xl overflow-hidden">
                <img
                  src={HERO_IMAGE}
                  alt="Infolib Interface"
                  className="w-full object-cover aspect-video"
                />
              </div>
              {/* Floating badge */}
              <div className="absolute -bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-card border shadow-lg px-6 py-2 flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                <span className="text-sm font-medium">System Online & Ready</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="relative py-24 sm:py-32">
        <div className="mx-auto max-w-7xl px-6">
          <div className="text-center mb-16">
            <h2 className="mb-4 text-3xl font-bold sm:text-4xl">
              Why Choose{" "}
              <span className="bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
                Infolib
              </span>
              ?
            </h2>
            <p className="mx-auto max-w-2xl text-muted-foreground text-lg">
              Built with cutting-edge technology and designed for the best user experience.
            </p>
          </div>

          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {[
              {
                icon: Brain,
                title: "Smart Conversations",
                description:
                  "Context-aware assistant that understands nuance and maintains coherent long conversations.",
                color: "primary",
              },
              {
                icon: Zap,
                title: "Lightning Fast",
                description:
                  "Near-instant responses with optimized inference. No waiting, just flowing conversation.",
                color: "secondary",
              },
              {
                icon: Shield,
                title: "Privacy First",
                description:
                  "Your conversations are encrypted and private. We never share your data with third parties.",
                color: "primary",
              },
              {
                icon: Globe,
                title: "Multilingual",
                description:
                  "Communicate in 50+ languages with native-level fluency and cultural understanding.",
                color: "secondary",
              },
              {
                icon: MessageSquare,
                title: "Session History",
                description:
                  "Pick up where you left off. All your conversations are saved and easily searchable.",
                color: "primary",
              },
              {
                icon: Sparkles,
                title: "Creative Mode",
                description:
                  "Switch between analytical and creative modes for different types of tasks and inspiration.",
                color: "secondary",
              },
            ].map((feature, i) => (
              <div
                key={feature.title}
                className="group rounded-2xl border border-border/50 bg-card/50 p-6 backdrop-blur-sm transition-all duration-300 hover:border-primary/30 hover:shadow-lg hover:-translate-y-1 animate-fade-in-up"
                style={{ animationDelay: `${i * 0.1}s` }}
              >
                <div
                  className={`mb-4 flex h-12 w-12 items-center justify-center rounded-xl ${
                    feature.color === "primary"
                      ? "bg-primary/10 text-primary"
                      : "bg-secondary/10 text-secondary"
                  }`}
                >
                  <feature.icon className="h-6 w-6" />
                </div>
                <h3 className="mb-2 text-lg font-semibold">{feature.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="relative py-24 sm:py-32">
        <div className="mx-auto max-w-7xl px-6">
          <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-primary via-primary/90 to-secondary p-12 sm:p-16 text-center">
            {/* Decorative elements */}
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
              <div className="absolute -top-20 -right-20 h-64 w-64 rounded-full bg-white/10 blur-2xl" />
              <div className="absolute -bottom-20 -left-20 h-64 w-64 rounded-full bg-white/5 blur-2xl" />
            </div>

            <div className="relative z-10">
              <h2 className="mb-4 text-3xl font-bold text-white sm:text-4xl">
                Ready to Transform Your Workflow?
              </h2>
              <p className="mx-auto mb-8 max-w-xl text-white/80 text-lg">
                Join thousands of users who are already more productive with Infolib.
                Start for free — no credit card required.
              </p>
              <Button
                size="lg"
                onClick={handleGetStarted}
                className="rounded-full px-8 py-6 text-base font-semibold bg-white text-primary hover:bg-white/90 gap-2 shadow-lg"
              >
                Get Started Now
                <ArrowRight className="h-5 w-5" />
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t py-12">
        <div className="mx-auto max-w-7xl px-6">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2.5">
              <img src={LOGO_IMAGE} alt="Infolib AI" className="h-6 w-6 rounded" />
              <span className="font-semibold text-sm">Infolib AI</span>
            </div>
            <p className="text-sm text-muted-foreground">
              © {new Date().getFullYear()} Infolib. Built with ❤️.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}