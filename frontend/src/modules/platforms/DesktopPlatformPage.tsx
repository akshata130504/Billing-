import { Monitor } from 'lucide-react';
import { PlatformPage } from './PlatformPage';

export function DesktopPlatformPage() {
  return (
    <PlatformPage
      family="desktop"
      uiKey="desktop"
      icon={<Monitor className="w-4 h-4" />}
    />
  );
}
