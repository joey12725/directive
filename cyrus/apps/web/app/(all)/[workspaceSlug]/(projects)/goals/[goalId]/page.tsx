import type { Route } from "./+types/page";
import { GoalDetail } from "@/components/goals";

export default function GoalDetailPage({ params }: Route.ComponentProps) {
  return <GoalDetail workspaceSlug={params.workspaceSlug} goalId={params.goalId} />;
}
