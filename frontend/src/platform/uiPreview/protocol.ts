/** postMessage protocol between the visual editor (parent) and the preview iframe. Same-origin
 *  only: both sides check event.origin and event.source before trusting a message. */
import type { PageConfigs, PageKey } from '../../appUi/registry';

export const PREVIEW_PATH = '/superadmin/ui-preview';

export interface RenderMessage {
  type: 'rb-ui-preview:render';
  page: PageKey;
  pages: PageConfigs;
  selectedId: string | null;
}
export interface ReadyMessage {
  type: 'rb-ui-preview:ready';
}
export interface SelectMessage {
  type: 'rb-ui-preview:select';
  id: string;
}

export function isRenderMessage(value: unknown): value is RenderMessage {
  const v = value as Partial<RenderMessage> | null;
  return !!v && v.type === 'rb-ui-preview:render' && typeof v.page === 'string' && typeof v.pages === 'object';
}
export function isSelectMessage(value: unknown): value is SelectMessage {
  const v = value as Partial<SelectMessage> | null;
  return !!v && v.type === 'rb-ui-preview:select' && typeof v.id === 'string' && v.id.length <= 120;
}
export function isReadyMessage(value: unknown): value is ReadyMessage {
  return !!value && (value as ReadyMessage).type === 'rb-ui-preview:ready';
}
