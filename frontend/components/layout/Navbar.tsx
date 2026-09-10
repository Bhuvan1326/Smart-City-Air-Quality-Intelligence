"use client";

import { Bell, Sun, Moon, LogOut, ChevronDown, X, Menu } from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/lib/store/auth";
import { useCityStore, SUPPORTED_CITIES } from "@/lib/store/city";
import { useWebSocket } from "@/hooks/useWebSocket";
import { cn, extractErrorMessage } from "@/lib/utils";
import { useState, useRef, useEffect } from "react";
import { authApi, notificationsApi, type AppNotification } from "@/lib/api/services";
import { useToast } from "@/components/ui/toaster";

export interface NavbarProps {
  onMenuClick?: () => void;
}

export function Navbar({ onMenuClick }: NavbarProps) {
  const { theme, setTheme } = useTheme();
  const { user, clearAuth } = useAuthStore();
  const { selectedCity, setCity } = useCityStore();
  const { isConnected } = useWebSocket(selectedCity);
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [cityMenuOpen, setCityMenuOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const notificationsRef = useRef<HTMLDivElement>(null);
  const notificationsButtonRef = useRef<HTMLButtonElement>(null);
  const notificationsPanelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
        setCityMenuOpen(false);
      }
      if (
        notificationsRef.current &&
        !notificationsRef.current.contains(e.target as Node)
      ) {
        setNotificationsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  useEffect(() => {
    if (!notificationsOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setNotificationsOpen(false);
        notificationsButtonRef.current?.focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [notificationsOpen]);

  useEffect(() => {
    if (notificationsOpen) {
      notificationsPanelRef.current?.focus();
    }
  }, [notificationsOpen]);

  const unreadCountQuery = useQuery({
    queryKey: ["notifications-unread-count"],
    queryFn: notificationsApi.unreadCount,
    refetchInterval: 60_000,
  });
  const unreadCount = unreadCountQuery.data?.unread_count ?? 0;

  const notificationsQuery = useQuery({
    queryKey: ["notifications"],
    queryFn: () => notificationsApi.list({ page: 1, page_size: 20 }),
    enabled: notificationsOpen,
  });

  const invalidateNotifications = () => {
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
    queryClient.invalidateQueries({ queryKey: ["notifications-unread-count"] });
  };

  const markReadMutation = useMutation({
    mutationFn: (id: string) => notificationsApi.markRead(id),
    onSuccess: invalidateNotifications,
    onError: (err: unknown) => {
      toast({
        title: "Couldn't update notification",
        description: extractErrorMessage(err),
        variant: "destructive",
      });
    },
  });

  const markAllReadMutation = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: invalidateNotifications,
    onError: (err: unknown) => {
      toast({
        title: "Couldn't mark all as read",
        description: extractErrorMessage(err),
        variant: "destructive",
      });
    },
  });

  const dismissMutation = useMutation({
    mutationFn: (id: string) => notificationsApi.dismiss(id),
    onSuccess: invalidateNotifications,
    onError: (err: unknown) => {
      toast({
        title: "Couldn't dismiss notification",
        description: extractErrorMessage(err),
        variant: "destructive",
      });
    },
  });

  const handleLogout = async () => {
    try { await authApi.logout(); } catch {}
    // BUG 014 defense-in-depth: clear the service worker's cached API
    // responses so a different user signing in on this browser afterward
    // can never be served this user's cached authenticated data.
    if (typeof navigator !== "undefined" && navigator.serviceWorker?.controller) {
      navigator.serviceWorker.controller.postMessage({ type: "CLEAR_API_CACHE" });
    }
    clearAuth();
    router.push("/login");
  };

  return (
    <header className="h-14 border-b border-border bg-card flex items-center justify-between px-4 gap-4">
      {onMenuClick && (
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Open navigation menu"
          className="p-2 -ml-1 rounded-lg hover:bg-accent transition-colors text-muted-foreground lg:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <Menu className="w-5 h-5" aria-hidden="true" />
        </button>
      )}

      {/* City selector */}
      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setCityMenuOpen(!cityMenuOpen)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-accent hover:bg-accent/80 text-sm font-medium transition-colors"
        >
          <span className="w-2 h-2 rounded-full bg-green-500" />
          {selectedCity}
          <ChevronDown className="w-3 h-3 text-muted-foreground" />
        </button>
        {cityMenuOpen && (
          <div className="absolute top-full mt-1 left-0 w-40 bg-card border border-border rounded-lg shadow-lg z-50 py-1">
            {SUPPORTED_CITIES.map((city) => (
              <button
                key={city}
                onClick={() => { setCity(city); setCityMenuOpen(false); }}
                className={cn(
                  "w-full text-left px-3 py-2 text-sm hover:bg-accent transition-colors",
                  city === selectedCity && "text-primary font-medium"
                )}
              >
                {city}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Right side controls */}
      <div className="flex items-center gap-2 ml-auto">
        {/* WS status */}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className={cn("w-1.5 h-1.5 rounded-full", isConnected ? "bg-green-500" : "bg-red-500")} />
          {isConnected ? "Live" : "Offline"}
        </div>

        {/* Theme toggle */}
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          className="p-2 rounded-lg hover:bg-accent transition-colors text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          {theme === "dark" ? <Sun className="w-4 h-4" aria-hidden="true" /> : <Moon className="w-4 h-4" aria-hidden="true" />}
        </button>

        {/* Notifications */}
        <div className="relative" ref={notificationsRef}>
          <button
            ref={notificationsButtonRef}
            type="button"
            id="notifications-trigger"
            aria-haspopup="dialog"
            aria-expanded={notificationsOpen}
            aria-controls="notifications-panel"
            aria-label={
              unreadCount > 0
                ? `Notifications, ${unreadCount} unread`
                : "Notifications, no unread"
            }
            onClick={() => setNotificationsOpen((open) => !open)}
            className="relative p-2 rounded-lg hover:bg-accent transition-colors text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <Bell className="w-4 h-4" aria-hidden="true" />
            {unreadCount > 0 && (
              <span
                aria-hidden="true"
                className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full"
              />
            )}
          </button>

          {notificationsOpen && (
            <div
              id="notifications-panel"
              ref={notificationsPanelRef}
              role="dialog"
              aria-label="Notifications"
              tabIndex={-1}
              className="absolute top-full mt-1 right-0 w-80 bg-card border border-border rounded-lg shadow-lg z-50 focus:outline-none"
            >
              <div className="flex items-center justify-between px-3 py-2 border-b border-border">
                <p className="text-sm font-semibold">Notifications</p>
                <button
                  type="button"
                  onClick={() => markAllReadMutation.mutate()}
                  disabled={unreadCount === 0 || markAllReadMutation.isPending}
                  className="text-xs font-medium text-primary hover:underline disabled:opacity-40 disabled:no-underline disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
                >
                  Mark all read
                </button>
              </div>

              {notificationsQuery.isLoading && (
                <p role="status" className="px-3 py-6 text-center text-xs text-muted-foreground">
                  Loading…
                </p>
              )}

              {notificationsQuery.isError && (
                <p role="status" className="px-3 py-6 text-center text-xs text-destructive">
                  Couldn&apos;t load notifications.
                </p>
              )}

              {notificationsQuery.data && notificationsQuery.data.items.length === 0 && (
                <p role="status" className="px-3 py-6 text-center text-xs text-muted-foreground">
                  No notifications yet.
                </p>
              )}

              {notificationsQuery.data && notificationsQuery.data.items.length > 0 && (
                <ul className="max-h-80 overflow-y-auto divide-y divide-border">
                  {notificationsQuery.data.items.map((n: AppNotification) => (
                    <li
                      key={n.id}
                      className={cn("flex items-start gap-2 px-3 py-2", !n.is_read && "bg-accent/40")}
                    >
                      <button
                        type="button"
                        onClick={() => !n.is_read && markReadMutation.mutate(n.id)}
                        className="flex-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded"
                        aria-label={`${n.title}: ${n.body}, ${n.is_read ? "read" : "unread"}`}
                      >
                        <p className="text-xs font-medium">{n.title}</p>
                        <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{n.body}</p>
                        <p className="text-[10px] text-muted-foreground mt-0.5">
                          {new Date(n.created_at).toLocaleTimeString()}
                        </p>
                      </button>
                      <button
                        type="button"
                        onClick={() => dismissMutation.mutate(n.id)}
                        aria-label={`Dismiss notification: ${n.title}`}
                        className="p-1 rounded hover:bg-accent text-muted-foreground flex-shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                      >
                        <X className="w-3 h-3" aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {/* User menu */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setUserMenuOpen(!userMenuOpen)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-accent transition-colors"
          >
            <div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center">
              <span className="text-xs font-bold text-primary-foreground">
                {user?.full_name?.charAt(0) ?? "U"}
              </span>
            </div>
            <div className="hidden sm:block text-left">
              <p className="text-xs font-medium leading-tight">{user?.full_name}</p>
              <p className="text-xs text-muted-foreground capitalize">{user?.role?.replace(/_/g, " ")}</p>
            </div>
          </button>
          {userMenuOpen && (
            <div className="absolute top-full mt-1 right-0 w-48 bg-card border border-border rounded-lg shadow-lg z-50 py-1">
              <div className="px-3 py-2 border-b border-border">
                <p className="text-sm font-medium">{user?.full_name}</p>
                <p className="text-xs text-muted-foreground">{user?.email}</p>
              </div>
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                <LogOut className="w-3.5 h-3.5" />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
