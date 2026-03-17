/**
 * Agent Registry
 *
 * Central export point for all agent runners.
 * Import this to get access to the configured agent factory.
 */

import { AgentFactory, getAgentFactory } from './factory.js';
import { ClaudeCodeRunner } from './claude-code.js';
import { OpenClawRunner } from './openclaw.js';
import { GeminiRunner } from './gemini.js';
// Import other runners as they're implemented:
// import { CodexRunner } from './codex.js';
// import { ACPXRunner } from './acpx.js';

/**
 * Initialize and return the configured agent factory
 *
 * All available agent runners are registered here.
 * To add a new agent:
 * 1. Import the runner class
 * 2. Add factory.register(new YourRunner())
 * 3. That's it!
 */
export function createAgentFactory(): AgentFactory {
  const factory = getAgentFactory();

  // Register all available runners
  factory.register(new ClaudeCodeRunner());
  factory.register(new OpenClawRunner());
  factory.register(new GeminiRunner());

  // Add new runners here as they're implemented:
  // factory.register(new CodexRunner());
  // factory.register(new ACPXRunner()); // Generic fallback

  return factory;
}

/**
 * Get a configured agent factory instance
 * This is the main export used by the relay
 */
export const agentFactory = createAgentFactory();

/**
 * Export types for use by consumers
 */
export { AgentRunner, type PromptRequest } from './base.js';
export { AgentFactory } from './factory.js';
export type * from '../types/agent-events.js';
