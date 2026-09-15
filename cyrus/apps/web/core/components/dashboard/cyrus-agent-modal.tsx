/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState, useRef, useEffect } from "react";
import { Dialog, EDialogWidth } from "@plane/propel/dialog";
import { Button } from "@plane/propel/button";
import { Bot, Send, X, Loader2 } from "lucide-react";
import { AIService } from "@/services/ai.service";

const aiService = new AIService();

interface CyrusAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
  workspaceSlug: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

export function CyrusAgentModal({ isOpen, onClose, workspaceSlug }: CyrusAgentModalProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "Hello! I'm the Cyrus Agent orchestrator. How can I help you manage your agents today?",
      timestamp: new Date(),
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (isOpen) {
      // Focus input when modal opens
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: inputValue,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setIsLoading(true);

    try {
      const response = await aiService.createAgentTask(workspaceSlug, {
        prompt: inputValue,
        task: "orchestrator_interaction",
      });

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: response?.response || response?.message || "Task received and processing.",
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: "Sorry, I encountered an error processing your request. Please try again.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
      console.error("Error calling Cyrus Agent:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleClearChat = () => {
    setMessages([
      {
        id: "welcome",
        role: "assistant",
        content: "Hello! I'm the Cyrus Agent orchestrator. How can I help you manage your agents today?",
        timestamp: new Date(),
      },
    ]);
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Panel width={EDialogWidth.XXL} position="center">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-subtle px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-accent-primary/10">
              <Bot className="h-5 w-5 text-accent-primary" />
            </div>
            <div>
              <Dialog.Title className="text-16 font-semibold text-primary">Cyrus Agent</Dialog.Title>
              <p className="text-12 text-secondary">Orchestrator Assistant</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={handleClearChat}>
              Clear Chat
            </Button>
            <button
              onClick={onClose}
              className="rounded-md p-1 hover:bg-surface-2 transition-colors"
              aria-label="Close"
            >
              <X className="h-5 w-5 text-secondary hover:text-primary" />
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="h-[500px] overflow-y-auto px-6 py-4 space-y-4 bg-surface-1">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-3 ${
                  message.role === "user"
                    ? "bg-accent-primary text-white"
                    : "bg-surface-2 text-primary border border-subtle"
                }`}
              >
                <p className="text-14 whitespace-pre-wrap">{message.content}</p>
                <p
                  className={`text-11 mt-1 ${
                    message.role === "user" ? "text-white/70" : "text-secondary"
                  }`}
                >
                  {message.timestamp.toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </p>
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="flex justify-start">
              <div className="max-w-[80%] rounded-lg px-4 py-3 bg-surface-2 border border-subtle">
                <div className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin text-accent-primary" />
                  <p className="text-14 text-secondary">Processing...</p>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-subtle px-6 py-4 bg-surface-1">
          <div className="flex items-center gap-3">
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Ask the orchestrator agent..."
              className="flex-1 rounded-md border border-subtle bg-surface-2 px-4 py-2.5 text-14 text-primary placeholder:text-secondary focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary transition-colors"
              disabled={isLoading}
            />
            <Button
              variant="primary"
              size="base"
              onClick={handleSendMessage}
              disabled={!inputValue.trim() || isLoading}
              prependIcon={isLoading ? <Loader2 className="animate-spin" /> : <Send />}
            >
              Send
            </Button>
          </div>
          <p className="text-11 text-secondary mt-2">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </Dialog.Panel>
    </Dialog>
  );
}
