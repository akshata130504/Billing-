import React, { useRef, useState, useEffect } from 'react';
import { Camera, Check, Trash2, Upload, X } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { useToast } from '../../components/common/Toast';
import { Button } from '../../components/common/Button';
import { userService } from '../../services/userService';
import { toApiError } from '../../services/apiClient';
import { initials } from '../../utils/format';

const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5 MB
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

export function ProfilePhotoUpload() {
  const { user, refreshMe } = useAuth();
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isRemoving, setIsRemoving] = useState(false);
  const [imageLoadFailed, setImageLoadFailed] = useState(false);

  // Clean up object URLs when previewUrl changes or component unmounts
  useEffect(() => {
    return () => {
      if (previewUrl && previewUrl.startsWith('blob:')) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  // Reset load failure flag if the user's avatar changes
  useEffect(() => {
    setImageLoadFailed(false);
  }, [user?.avatar_url]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValidationError(null);
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate type
    if (!ALLOWED_TYPES.includes(file.type.toLowerCase())) {
      const ext = file.name.split('.').pop()?.toLowerCase();
      if (!['jpg', 'jpeg', 'png', 'webp'].includes(ext || '')) {
        setValidationError('Only JPG, PNG, and WEBP image files are supported.');
        showToast('error', 'Invalid file type', 'Please select a JPG, PNG, or WEBP image.');
        if (fileInputRef.current) fileInputRef.current.value = '';
        return;
      }
    }

    // Validate size (5 MB)
    if (file.size > MAX_FILE_SIZE) {
      setValidationError(`Image size exceeds 5 MB limit (${(file.size / (1024 * 1024)).toFixed(1)} MB).`);
      showToast('error', 'File too large', 'Image size must not exceed 5 MB.');
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    setSelectedFile(file);
    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);
    setImageLoadFailed(false);
  };

  const handleCancelPreview = () => {
    if (previewUrl && previewUrl.startsWith('blob:')) {
      URL.revokeObjectURL(previewUrl);
    }
    setPreviewUrl(null);
    setSelectedFile(null);
    setValidationError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    setValidationError(null);
    try {
      await userService.uploadAvatar(selectedFile);
      await refreshMe();
      showToast('success', 'Photo uploaded', 'Your profile photo has been updated.');
      handleCancelPreview();
    } catch (err: any) {
      const msg = toApiError(err).message || 'Failed to upload profile photo.';
      setValidationError(msg);
      showToast('error', 'Upload failed', msg);
    } finally {
      setIsUploading(false);
    }
  };

  const handleRemove = async () => {
    if (!user?.avatar_url) return;

    setIsRemoving(true);
    setValidationError(null);
    try {
      await userService.deleteAvatar();
      await refreshMe();
      showToast('info', 'Photo removed', 'Your profile photo has been removed.');
      handleCancelPreview();
    } catch (err: any) {
      const msg = toApiError(err).message || 'Failed to remove profile photo.';
      setValidationError(msg);
      showToast('error', 'Removal failed', msg);
    } finally {
      setIsRemoving(false);
    }
  };

  const triggerPicker = () => {
    if (isUploading || isRemoving) return;
    fileInputRef.current?.click();
  };

  const currentDisplayUrl = previewUrl || (imageLoadFailed ? null : user?.avatar_url);
  const hasPhoto = Boolean(user?.avatar_url);
  const isPreviewing = Boolean(previewUrl && selectedFile);

  return (
    <div className="flex flex-col sm:flex-row items-start sm:items-center gap-5 p-4 rounded-xl bg-slate-50/70 border border-slate-200/80 mb-6">
      {/* Hidden File Input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={handleFileChange}
        className="hidden"
        aria-label="Upload profile photo"
      />

      {/* Circular Avatar Container */}
      <div className="relative group shrink-0">
        <div className="w-20 h-20 rounded-full overflow-hidden border-2 border-white shadow-md bg-gradient-to-br from-[#D81B60] to-[#AD1457] flex items-center justify-center text-white font-bold text-xl select-none">
          {currentDisplayUrl ? (
            <img
              src={currentDisplayUrl}
              alt={user?.full_name || 'Profile photo'}
              className="w-full h-full object-cover"
              onError={() => setImageLoadFailed(true)}
            />
          ) : (
            <span>{initials(user?.full_name, user?.email?.[0]?.toUpperCase() ?? '?')}</span>
          )}
        </div>

        {/* Camera overlay hover icon */}
        {!isPreviewing && (
          <button
            type="button"
            onClick={triggerPicker}
            disabled={isUploading || isRemoving}
            title={hasPhoto ? 'Change Photo' : 'Upload Photo'}
            className="absolute inset-0 rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white cursor-pointer disabled:pointer-events-none"
          >
            <Camera className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Details & Actions */}
      <div className="flex-1 min-w-0 space-y-1.5">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-bold text-[#11194F]">Profile Photo</h4>
          {isPreviewing && (
            <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
              Preview
            </span>
          )}
        </div>
        <p className="text-xs text-[#59617D]">
          Accepts JPG, PNG, or WEBP up to 5 MB. Displayed on your team profile and header.
        </p>

        {validationError && (
          <p className="text-xs text-rose-600 font-medium">{validationError}</p>
        )}

        <div className="flex flex-wrap items-center gap-2.5 pt-2">
          {isPreviewing ? (
            <>
              <Button
                type="button"
                size="sm"
                variant="primary"
                onClick={handleUpload}
                isLoading={isUploading}
                disabled={isUploading}
                leadingIcon={<Check className="w-3.5 h-3.5" />}
              >
                Save Photo
              </Button>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={handleCancelPreview}
                disabled={isUploading}
                leadingIcon={<X className="w-3.5 h-3.5" />}
              >
                Cancel
              </Button>
            </>
          ) : (
            <>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={triggerPicker}
                disabled={isUploading || isRemoving}
                leadingIcon={<Upload className="w-3.5 h-3.5 text-[#D81B60]" />}
              >
                {hasPhoto ? 'Change Photo' : 'Upload Photo'}
              </Button>

              {hasPhoto && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={handleRemove}
                  isLoading={isRemoving}
                  disabled={isUploading || isRemoving}
                  className="text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                  leadingIcon={<Trash2 className="w-3.5 h-3.5" />}
                >
                  Remove Photo
                </Button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
