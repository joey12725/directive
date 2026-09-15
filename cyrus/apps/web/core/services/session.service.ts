/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";
import type { Session } from "@/components/sessions/types";

export class SessionService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async getSession(workspaceSlug: string, sessionId: string): Promise<Session> {
    return this.get(`/api/workspaces/${workspaceSlug}/cyrus/sessions/${sessionId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response;
      });
  }

  async listSessions(workspaceSlug: string): Promise<{ results: Session[] }> {
    return this.get(`/api/workspaces/${workspaceSlug}/cyrus/sessions/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response;
      });
  }
}

export const sessionService = new SessionService();
