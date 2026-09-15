/**
 * Reusable placeholder for Cyrus settings pages that haven't been built yet.
 */

import { Construction } from "lucide-react";
import { Card } from "@plane/propel/card";
import type { LucideIcon } from "lucide-react";

interface PlaceholderPageProps {
  title: string;
  description: string;
  icon?: LucideIcon;
}

export function PlaceholderPage({ title, description, icon: Icon = Construction }: PlaceholderPageProps) {
  return (
    <div className="flex-1 overflow-y-auto p-6">
      <h1 className="text-body-xl-medium text-primary mb-2">{title}</h1>
      <p className="text-body-sm text-tertiary mb-6">{description}</p>

      <Card className="!py-12">
        <div className="flex flex-col items-center justify-center text-center">
          <div className="rounded-full bg-layer-2 p-4 mb-4">
            <Icon className="size-8 text-tertiary" />
          </div>
          <h2 className="text-body-md-medium text-primary mb-2">Coming Soon</h2>
          <p className="text-body-sm text-tertiary max-w-md">
            This settings page is under construction. Configuration for {title.toLowerCase()} will be available in a
            future update.
          </p>
        </div>
      </Card>
    </div>
  );
}
