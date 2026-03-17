# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path


from plane.app.views import (
    CyrusAgentProjectEndpoint,
    CyrusAgentWorkspaceEndpoint,
    GPTIntegrationEndpoint,
    UnsplashEndpoint,
    WorkspaceGPTIntegrationEndpoint,
)


urlpatterns = [
    path("unsplash/", UnsplashEndpoint.as_view(), name="unsplash"),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/ai-assistant/",
        CyrusAgentProjectEndpoint.as_view(),
        name="importer",
    ),
    path(
        "workspaces/<str:slug>/ai-assistant/",
        CyrusAgentWorkspaceEndpoint.as_view(),
        name="importer",
    ),
    # Compatibility routes for older callers while the Cyrus fork migrates.
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/cyrus-agent/",
        GPTIntegrationEndpoint.as_view(),
        name="cyrus-agent-project",
    ),
    path(
        "workspaces/<str:slug>/cyrus-agent/",
        WorkspaceGPTIntegrationEndpoint.as_view(),
        name="cyrus-agent-workspace",
    ),
]
