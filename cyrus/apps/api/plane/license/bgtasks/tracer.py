# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from celery import shared_task
from opentelemetry import trace

# Module imports
from plane.license.models import Instance
from plane.db.models import (
    User,
    Workspace,
    Project,
    Issue,
    Module,
    Cycle,
    CycleIssue,
    ModuleIssue,
    Page,
    WorkspaceMember,
)
from plane.utils.telemetry import init_tracer, shutdown_tracer


@shared_task
def instance_traces():
    return
