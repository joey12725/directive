import type { Route } from "./+types/page";
import { PoolsList } from "@/components/cyrus-lists";

export default function PoolsPage({ params }: Route.ComponentProps) {
  return <PoolsList workspaceSlug={params.workspaceSlug} />;
}
