/**
 * Agent Factory
 *
 * Central registry and factory for agent runners.
 * Routes agent requests to the appropriate implementation.
 *
 * To add a new agent:
 * 1. Create a class extending AgentRunner
 * 2. Register it in the factory constructor
 * 3. That's it! The relay will automatically use it.
 */

import type { AgentRunner } from './base.js';

export class AgentFactory {
  private runners: AgentRunner[] = [];

  /**
   * Register an agent runner
   */
  register(runner: AgentRunner): void {
    this.runners.push(runner);
  }

  /**
   * Get the runner for a given agent name
   *
   * @param agent - Agent identifier (e.g., 'claude', 'openclaw')
   * @returns AgentRunner instance or undefined if not found
   */
  getRunner(agent: string): AgentRunner | undefined {
    return this.runners.find(runner => runner.canHandle(agent));
  }

  /**
   * Get all registered agent names
   */
  getAgentNames(): string[] {
    return this.runners.map(runner => runner.name);
  }

  /**
   * Check if an agent is supported
   */
  isSupported(agent: string): boolean {
    return this.getRunner(agent) !== undefined;
  }
}

/**
 * Global agent factory instance
 * Initialized with all available runners
 */
let globalFactory: AgentFactory | null = null;

/**
 * Get the global agent factory
 * Lazy initialization to avoid circular dependencies
 */
export function getAgentFactory(): AgentFactory {
  if (!globalFactory) {
    globalFactory = new AgentFactory();
    // Runners will be registered by their modules
  }
  return globalFactory;
}
