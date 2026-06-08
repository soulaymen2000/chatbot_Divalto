import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAppStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ThemeToggle } from "@/components/ChatUI";
import { Sparkles, ArrowLeft, Mail, Lock, User, AlertCircle } from "lucide-react";

const LOGO_IMAGE =
  "https://mgx-backend-cdn.metadl.com/generate/images/1156904/2026-04-26/nmkkosyaafmq/logo-novamind-icon.png"; // Placeholder logo

export default function AuthPage() {
  const navigate = useNavigate();
  const { signIn, signUp, isAuthenticated, authLoading, authError } = useAppStore();

  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [localError, setLocalError] = useState("");

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate("/chat");
    }
  }, [isAuthenticated, navigate]);

  if (isAuthenticated) {
    return null;
  }

  const error = localError || authError;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError("");

    if (mode === "signup" && password !== confirmPassword) {
      setLocalError("Passwords do not match.");
      return;
    }
    if (password.length < 6) {
      setLocalError("Password must be at least 6 characters.");
      return;
    }

    let success = false;
    if (mode === "signin") {
      success = await signIn(email, password);
    } else {
      success = await signUp(name, email, password);
    }

    if (success) {
      navigate("/chat");
    }
  };

  const switchMode = () => {
    setMode(mode === "signin" ? "signup" : "signin");
    setLocalError("");
    setName("");
    setEmail("");
    setPassword("");
    setConfirmPassword("");
  };

  return (
    <div className="relative flex min-h-screen">
      {/* Left Panel — Decorative */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-gradient-to-br from-primary via-primary/90 to-secondary">
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute -top-20 -right-20 h-96 w-96 rounded-full bg-white/10 blur-3xl animate-float" />
          <div className="absolute -bottom-20 -left-20 h-96 w-96 rounded-full bg-white/5 blur-3xl animate-float" style={{ animationDelay: "3s" }} />
          <div className="absolute top-1/3 right-1/4 h-64 w-64 rounded-full bg-secondary/20 blur-2xl animate-spin-slow" />
        </div>

        <div className="relative z-10 flex flex-col justify-center px-16 text-white">
          <div className="mb-8 flex items-center gap-3">
            <img src={LOGO_IMAGE} alt="Infolib AI" className="h-12 w-12 rounded-xl" />
            <span className="text-3xl font-bold">Infolib AI</span>
          </div>
          <h1 className="mb-4 text-4xl font-extrabold leading-tight">
            Unlock the Power of
            <br />
            <span className="text-white/90">AI Conversation</span>
          </h1>
          <p className="max-w-md text-lg text-white/75 leading-relaxed">
            Join users who are already transforming their productivity with intelligent assistance.
          </p>

          <div className="mt-10 space-y-4">
            {[
              "Context-aware intelligent responses",
              "50+ language support",
              "End-to-end encrypted conversations",
              "Creative and analytical modes",
            ].map((feature) => (
              <div key={feature} className="flex items-center gap-3">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-white/20">
                  <Sparkles className="h-3.5 w-3.5" />
                </div>
                <span className="text-white/85 text-sm">{feature}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right Panel — Auth Form */}
      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between p-6">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/")}
            className="gap-2 text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          <ThemeToggle />
        </div>

        <div className="flex flex-1 items-center justify-center px-6 py-12">
          <div className="w-full max-w-md animate-fade-in-up">
            <div className="mb-8 flex items-center gap-2.5 lg:hidden">
              <img src={LOGO_IMAGE} alt="Infolib AI" className="h-8 w-8 rounded-lg" />
              <span className="text-xl font-bold bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
                Infolib AI
              </span>
            </div>

            <div className="mb-8">
              <h2 className="text-2xl font-bold">
                {mode === "signin" ? "Welcome back" : "Create your account"}
              </h2>
              <p className="mt-2 text-muted-foreground">
                {mode === "signin"
                  ? "Sign in to continue your conversations"
                  : "Start your journey with Infolib"}
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              {mode === "signup" && (
                <div className="space-y-2">
                  <Label htmlFor="name">Full Name</Label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="name"
                      type="text"
                      placeholder="John Doe"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="pl-10 h-11 rounded-xl"
                      required
                    />
                  </div>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="email"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="pl-10 h-11 rounded-xl"
                    required
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="password"
                    type="password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="pl-10 h-11 rounded-xl"
                    required
                    minLength={6}
                  />
                </div>
              </div>

              {mode === "signup" && (
                <div className="space-y-2">
                  <Label htmlFor="confirmPassword">Confirm Password</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="confirmPassword"
                      type="password"
                      placeholder="••••••••"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      className="pl-10 h-11 rounded-xl"
                      required
                      minLength={6}
                    />
                  </div>
                </div>
              )}

              {error && (
                <div className="flex items-start gap-2 rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive animate-fade-in">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  {error}
                </div>
              )}

              <Button
                type="submit"
                id="auth-submit-btn"
                className="w-full h-11 rounded-xl font-semibold gap-2"
                disabled={authLoading}
              >
                {authLoading ? (
                  <div className="flex items-center gap-2">
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    {mode === "signin" ? "Signing in..." : "Creating account..."}
                  </div>
                ) : (
                  <>
                    {mode === "signin" ? "Sign In" : "Create Account"}
                    <Sparkles className="h-4 w-4" />
                  </>
                )}
              </Button>
            </form>


            <p className="mt-8 text-center text-sm text-muted-foreground">
              {mode === "signin" ? "Don't have an account? " : "Already have an account? "}
              <button
                type="button"
                onClick={switchMode}
                className="font-semibold text-primary hover:underline"
              >
                {mode === "signin" ? "Sign up" : "Sign in"}
              </button>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}