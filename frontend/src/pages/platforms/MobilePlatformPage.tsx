import { Smartphone } from 'lucide-react';
import { PlatformPage } from './PlatformPage';

export function MobilePlatformPage() {
  return (
    <PlatformPage
      family="mobile"
      title="Mobile"
      subtitle="iOS and Android companion clients: registered devices, trust status, and the bootstrap contract they consume from this API."
      icon={<Smartphone className="w-4 h-4" />}
    />
  );
}
