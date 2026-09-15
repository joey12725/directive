import type { Route } from "./+types/page";
import { SessionsList } from "@/components/cyrus-lists";

export default function SessionsListPage({ params }: Route.ComponentProps) {
  return <SessionsList workspaceSlug={params.workspaceSlug} />;
}
