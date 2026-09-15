import type { Route } from "./+types/page";
import { GoalsList } from "@/components/cyrus-lists";

export default function GoalsPage({ params }: Route.ComponentProps) {
  return <GoalsList workspaceSlug={params.workspaceSlug} />;
}
