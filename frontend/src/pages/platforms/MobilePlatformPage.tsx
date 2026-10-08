import { Smartphone } from 'lucide-react';
import { PlatformPage } from './PlatformPage';

export function MobilePlatformPage() {
  return (
    <PlatformPage
      family="mobile"
      uiKey="mobile"
      icon={<Smartphone className="w-4 h-4" />}
    />
  );
}
