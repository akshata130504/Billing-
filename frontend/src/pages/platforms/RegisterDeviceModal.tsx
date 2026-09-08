import React, { useEffect, useState } from 'react';
import { Wand2 } from 'lucide-react';
import { Modal } from '../../components/common/Modal';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { Select } from '../../components/common/Select';
import { useToast } from '../../components/common/Toast';
import { fieldErrors } from '../../services/apiClient';
import { deviceService } from '../../services/deviceService';
import {
  PLATFORM_LABELS,
  type DeviceOut,
  type DevicePlatform,
  type DeviceRegisterIn,
} from '../../types/devices';

export interface RegisterDeviceModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Platforms offered in the dropdown (the page's platform family). */
  platforms: DevicePlatform[];
  onRegistered: (device: DeviceOut) => void;
}

function randomIdentifier(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {
    // fall through
  }
  return `dev-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

const emptyForm = (platform: DevicePlatform) => ({
  device_identifier: '',
  platform,
  device_name: '',
  os_version: '',
  app_version: '',
  push_token: '',
});

export function RegisterDeviceModal({ isOpen, onClose, platforms, onRegistered }: RegisterDeviceModalProps) {
  const { showToast } = useToast();
  const [form, setForm] = useState(() => emptyForm(platforms[0]));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setForm(emptyForm(platforms[0]));
      setErrors({});
    }
  }, [isOpen, platforms]);

  const update = (key: keyof typeof form, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) setErrors((prev) => ({ ...prev, [key]: '' }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const identifier = form.device_identifier.trim();
    if (!identifier) {
      setErrors({ device_identifier: 'A device identifier is required.' });
      return;
    }
    const body: DeviceRegisterIn = {
      device_identifier: identifier,
      platform: form.platform,
      device_name: form.device_name.trim() || null,
      os_version: form.os_version.trim() || null,
      app_version: form.app_version.trim() || null,
      push_token: form.push_token.trim() || null,
    };
    try {
      setSaving(true);
      const device = await deviceService.register(body);
      showToast('success', `Registered ${device.device_name || PLATFORM_LABELS[device.platform]} device`);
      onRegistered(device);
      onClose();
    } catch (err: any) {
      setErrors(fieldErrors(err));
      showToast('error', err.message || 'Failed to register device');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Register device"
      description="Creates a trusted device record for your account. Native clients normally do this automatically during sign-in."
      size="md"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Input
              label="Device identifier"
              placeholder="Stable per-install ID (e.g. a UUID)"
              value={form.device_identifier}
              onChange={(e) => update('device_identifier', e.target.value)}
              error={errors.device_identifier}
              helperText={errors.device_identifier ? undefined : 'Unique per user. A revoked identifier cannot be re-used.'}
              maxLength={255}
              required
            />
          </div>
          <Button
            type="button"
            variant="outline"
            size="md"
            className="mb-[1.35rem]"
            onClick={() => update('device_identifier', randomIdentifier())}
            leadingIcon={<Wand2 className="w-4 h-4" />}
          >
            Generate
          </Button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Select
            label="Platform"
            value={form.platform}
            onChange={(e) => update('platform', e.target.value)}
            options={platforms.map((p) => ({ value: p, label: PLATFORM_LABELS[p] }))}
            error={errors.platform}
            required
          />
          <Input
            label="Device name"
            placeholder="e.g. Priya's iPhone"
            value={form.device_name}
            onChange={(e) => update('device_name', e.target.value)}
            error={errors.device_name}
            maxLength={150}
          />
          <Input
            label="OS version"
            placeholder="e.g. 17.5"
            value={form.os_version}
            onChange={(e) => update('os_version', e.target.value)}
            error={errors.os_version}
            maxLength={50}
          />
          <Input
            label="App version"
            placeholder="e.g. 1.0.0"
            value={form.app_version}
            onChange={(e) => update('app_version', e.target.value)}
            error={errors.app_version}
            maxLength={50}
          />
        </div>

        <Input
          label="Push token"
          placeholder="Optional — APNs / FCM / WNS token"
          value={form.push_token}
          onChange={(e) => update('push_token', e.target.value)}
          error={errors.push_token}
          helperText="Stored for future push notifications; cleared automatically when the device is revoked."
          maxLength={500}
        />

        <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
          <Button variant="ghost" size="sm" type="button" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" type="submit" isLoading={saving}>
            Register device
          </Button>
        </div>
      </form>
    </Modal>
  );
}
