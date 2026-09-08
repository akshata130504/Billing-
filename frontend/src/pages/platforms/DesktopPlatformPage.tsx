import { Monitor } from 'lucide-react';
import { PlatformPage } from './PlatformPage';

export function DesktopPlatformPage() {
  return (
    <PlatformPage
      family="desktop"
      title="Desktop"
      subtitle="Windows and macOS shells: registered devices, trust status, and how the thin desktop client signs in against this API."
      icon={<Monitor className="w-4 h-4" />}
    />
  );
}
