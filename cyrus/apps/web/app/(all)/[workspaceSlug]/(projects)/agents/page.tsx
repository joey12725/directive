import type { Route } from "./+types/page";
import { AgentsList } from "@/components/cyrus-lists";

export default function AgentsPage({ params }: Route.ComponentProps) {
  return <AgentsList workspaceSlug={params.workspaceSlug} />;
}
