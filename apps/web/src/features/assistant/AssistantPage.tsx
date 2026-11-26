import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { problemMessage } from "@/lib/api";
import { askEil, type AskEilResponse } from "@/lib/api/assistant";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  citations?: AskEilResponse["citations"];
}

export function AssistantPage() {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async () => {
    const question = input.trim();
    if (!question || busy) return;
    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setBusy(true);
    try {
      const response = await askEil(question);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: response.answer, citations: response.citations },
      ]);
      if (response.tool_log.length > 0) {
        const toolsUsed = response.tool_log.map((row) => row.name).join(", ");
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: t("assistant.toolsUsed") + ": " + toolsUsed },
        ]);
      }
    } catch (cause) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: problemMessage(cause, t("common.error")) },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">{t("assistant.title")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("assistant.subtitle")}</p>
      </div>
      <Card className="flex h-[60vh] flex-col">
        <CardHeader>
          <CardTitle className="text-base">{t("assistant.chat")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-1 flex-col space-y-3 overflow-y-auto">
          {messages.length === 0 ? (
            <p className="text-sm text-muted-foreground" data-testid="assistant-empty">
              {t("assistant.empty")}
            </p>
          ) : null}
          {messages.map((message, index) => (
            <div
              key={index}
              data-testid="assistant-message"
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-lg px-4 py-2 text-sm ${
                  message.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"
                }`}
              >
                {message.text}
                {message.citations && message.citations.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    {message.citations.map((citation) => (
                      <Link key={citation.id} to={`/items/${citation.id}`} className="underline">
                        {citation.id.slice(0, 8)}
                      </Link>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          ))}
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
        </CardContent>
      </Card>
      <div className="flex items-center gap-2">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void send();
          }}
          placeholder={t("assistant.inputPlaceholder")}
          className="h-9 flex-1 rounded-md border bg-background px-3 text-sm"
          aria-label={t("assistant.inputPlaceholder")}
        />
        <Button size="sm" disabled={busy || !input.trim()} onClick={() => void send()}>
          {t("assistant.send")}
        </Button>
      </div>
    </div>
  );
}
