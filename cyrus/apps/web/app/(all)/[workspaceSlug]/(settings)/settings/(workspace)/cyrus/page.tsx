import { Settings } from "lucide-react";
import { PlaceholderPage } from "@/components/cyrus-settings";

export default function CyrusGeneralSettingsPage() {
  return (
    <PlaceholderPage
      title="General"
      description="Global Cyrus orchestration settings for this workspace."
      icon={Settings}
    />
  );
}
