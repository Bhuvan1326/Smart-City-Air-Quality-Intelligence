"use client";

import { useState, useRef, useEffect } from "react";
import { assistantApi } from "@/lib/api/services";
import type { AssistantResponse } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { Send, Bot, User, Loader2, Map, Info } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: AssistantResponse;
  timestamp: Date;
}

const SAMPLE_QUERIES = [
  "Why is AQI increasing in Ward 7?",
  "Which industries contributed most to pollution yesterday?",
  "Show top pollution hotspots right now.",
  "Recommend actions to reduce PM2.5 in Shivajinagar.",
  "What changed in air quality after yesterday's inspections?",
  "Forecast AQI for tomorrow morning across all wards.",
];

export default function AssistantPage() {
  const { selectedCity } = useCityStore();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "0",
      role: "assistant",
      content: `Hello! I'm your AI air quality analyst for ${selectedCity}. I can answer questions about live AQI data, pollution sources, forecast trends, and enforcement actions. What would you like to know?`,
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const history = messages.slice(-10).map((m) => ({ role: m.role, content: m.content }));
      const response = await assistantApi.chat(text, selectedCity, history);

      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: response.answer,
        response,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: unknown) {
      const detail =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      const errMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: detail ?? "I'm unable to process that request. Please ensure ANTHROPIC_API_KEY is configured.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full max-h-[calc(100vh-8rem)] bg-background">
      <div className="mb-4">
        <h1 className="text-2xl font-bold">AI Assistant</h1>
        <p className="text-sm text-muted-foreground">Ask natural language questions about {selectedCity}&apos;s air quality</p>
      </div>

      <div className="flex gap-4 flex-1 min-h-0">
        {/* Chat */}
        <div className="flex flex-col flex-1 min-w-0 rounded-xl border border-border bg-card overflow-hidden">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((msg) => (
              <div key={msg.id} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                  msg.role === "user" ? "bg-primary" : "bg-muted"
                }`}>
                  {msg.role === "user"
                    ? <User className="w-4 h-4 text-primary-foreground" />
                    : <Bot className="w-4 h-4 text-muted-foreground" />
                  }
                </div>
                <div className={`flex flex-col max-w-[75%] ${msg.role === "user" ? "items-end" : ""}`}>
                  <div className={`rounded-xl px-4 py-3 text-sm ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-foreground"
                  }`}>
                    <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                  </div>

                  {/* Evidence & metadata for assistant responses */}
                  {msg.response && (
                    <div className="mt-2 space-y-2 w-full">
                      {/* Confidence */}
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <Info className="w-3 h-3" />
                        <span>Confidence: {Math.round(msg.response.confidence_score * 100)}%</span>
                        <span>·</span>
                        <span>Sources: {msg.response.data_sources.join(", ")}</span>
                      </div>

                      {/* Evidence cards */}
                      {msg.response.supporting_evidence.length > 0 && (
                        <div className="rounded-lg border border-border p-3 space-y-1.5">
                          <p className="text-xs font-medium text-muted-foreground">Supporting evidence</p>
                          {msg.response.supporting_evidence.map((ev, i) => (
                            <div key={i} className="flex items-center justify-between text-xs">
                              <span className="text-muted-foreground">{ev.station}</span>
                              <span className="font-medium">AQI {ev.aqi}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Map data summary */}
                      {msg.response.map_data && (
                        <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <Map className="w-3.5 h-3.5 text-primary" />
                            <p className="text-xs font-medium text-primary">Spatial data available</p>
                          </div>
                          <div className="grid grid-cols-2 gap-1">
                            {msg.response.map_data.points?.slice(0, 4).map((pt, i) => (
                              <div key={i} className="text-xs text-muted-foreground">
                                Ward {pt.ward_id}: <span className="font-medium text-foreground">AQI {pt.aqi}</span>
                              </div>
                            ))}
                          </div>
                          <p className="text-xs text-muted-foreground mt-1">View on Live AQI → Heatmap for full map</p>
                        </div>
                      )}

                      {/* Reasoning trace */}
                      <details className="text-xs">
                        <summary className="text-muted-foreground cursor-pointer hover:text-foreground">
                          Reasoning trace
                        </summary>
                        <p className="mt-1 text-muted-foreground pl-2 border-l border-border">{msg.response.reasoning_trace}</p>
                      </details>
                    </div>
                  )}

                  <p className="text-xs text-muted-foreground mt-1">
                    {formatDistanceToNow(msg.timestamp, { addSuffix: true })}
                  </p>
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center">
                  <Bot className="w-4 h-4 text-muted-foreground" />
                </div>
                <div className="bg-muted rounded-xl px-4 py-3 flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">Analysing data...</span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="border-t border-border p-4">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(input); } }}
                placeholder="Ask about air quality, sources, forecasts, enforcement..."
                className="flex-1 px-4 py-2.5 rounded-lg bg-background border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary transition-all"
              />
              <button
                onClick={() => sendMessage(input)}
                disabled={!input.trim() || isLoading}
                className="px-4 py-2.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Sample queries sidebar */}
        <div className="w-56 flex-shrink-0 space-y-3">
          <h3 className="text-sm font-semibold text-muted-foreground">Example queries</h3>
          {SAMPLE_QUERIES.map((q) => (
            <button
              key={q}
              onClick={() => sendMessage(q)}
              disabled={isLoading}
              className="w-full text-left text-xs px-3 py-2.5 rounded-lg border border-border hover:bg-accent hover:border-primary/30 transition-colors text-muted-foreground hover:text-foreground disabled:opacity-50"
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
