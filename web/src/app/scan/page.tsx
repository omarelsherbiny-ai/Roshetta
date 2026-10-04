// web/src/app/scan/page.tsx (route: /scan — document capture preview, OCR disabled)
'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useLanguage } from '@/lib/i18n';

type DocType = 'prescription' | 'invoice' | 'receipt';

// `torch` is not in the TypeScript DOM typings yet, but Chromium-based browsers report it.
type TorchCapabilities = MediaTrackCapabilities & { torch?: boolean };
type TorchConstraintSet = MediaTrackConstraintSet & { torch?: boolean };

export default function ScanPage() {
  const router = useRouter();
  const { isRTL, dir, t } = useLanguage();
  const docTitles: Record<DocType, string> = { prescription: t('sc_title_rx'), invoice: t('sc_title_invoice'), receipt: t('sc_title_receipt') };
  const docTags: Record<DocType, string> = { prescription: t('sc_tag_rx'), invoice: t('sc_tag_invoice'), receipt: t('sc_tag_receipt') };
  const docNames: Record<DocType, string> = { prescription: t('sc_tab_rx'), invoice: t('sc_tab_invoice'), receipt: t('sc_tab_receipt') };

  const [docType, setDocType] = useState<DocType>('prescription');
  const [isTorchOn, setIsTorchOn] = useState(false);
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [isTrayOpen, setIsTrayOpen] = useState(false);
  const [toast, setToast] = useState<{ message: string; icon: string } | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const showToast = (message: string, icon: string = 'check_circle') => {
    setToast({ message, icon });
    setTimeout(() => setToast(null), 2500);
  };

  // Start live camera
  useEffect(() => {
    let active = true;

    async function startCamera() {
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } },
          audio: false,
        });
        if (active && videoRef.current) {
          videoRef.current.srcObject = stream;
          streamRef.current = stream;
        }
      } catch (err) {
        console.warn('Live camera access error or unpermitted:', err);
      }
    }

    startCamera();

    return () => {
      active = false;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
    };
  }, []);

  // Shutter capture from live camera or fallback
  const handleCapture = () => {
    if (videoRef.current && canvasRef.current && streamRef.current) {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
        setCapturedImage(dataUrl);

        setIsTrayOpen(true);
        showToast(t('sc_img_captured'), 'photo_camera');
        return;
      }
    }

    // If live video not active, trigger file input
    fileInputRef.current?.click();
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      setCapturedImage(reader.result as string);
      setIsTrayOpen(true);
      showToast(t('sc_img_loaded'), 'image');
    };
    reader.readAsDataURL(file);
  };

  const toggleTorch = async () => {
    setIsTorchOn(!isTorchOn);
    if (streamRef.current) {
      const track = streamRef.current.getVideoTracks()[0];
      const capabilities: TorchCapabilities = track.getCapabilities ? (track.getCapabilities() as TorchCapabilities) : {};
      if (capabilities.torch) {
        try {
          const torchConstraint: TorchConstraintSet = { torch: !isTorchOn };
          await track.applyConstraints({ advanced: [torchConstraint] });
          showToast(!isTorchOn ? t('sc_torch_on') : t('sc_torch_off'), 'flashlight_on');
        } catch {}
      } else {
        showToast(!isTorchOn ? t('sc_torch_unsupported') : t('sc_torch_off'), 'lightbulb');
      }
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-surface text-on-surface select-none" dir={dir}>
      {/* ── Top Header ── */}
      <header className="fixed top-0 w-full z-50 bg-surface/80 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.04)] pt-safe">
        <div className="h-16 px-margin-mobile flex items-center justify-between gap-space-sm">
          <div className="flex items-center gap-space-sm">
            <button
              aria-label={t('back')}
              onClick={() => router.back()}
              className="w-touch-target-min h-touch-target-min flex items-center justify-center rounded-full text-on-surface hover:text-primary hover:bg-surface-container-high transition-colors"
            >
              <span className="material-symbols-outlined text-[24px]">{isRTL ? 'arrow_forward' : 'arrow_back'}</span>
            </button>
            <img
              alt="Roshetta"
              className="h-8 w-8 object-contain rounded-lg"
              src="/logo.svg"
            />
            <h1 className="font-headline-sm text-headline-sm text-on-surface">
              {docTitles[docType]}
            </h1>
          </div>
          <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center">
            <span className="material-symbols-outlined text-on-primary text-[18px]">person</span>
          </div>
        </div>
      </header>

      {/* ── Hidden Canvas & File Picker ── */}
      <canvas ref={canvasRef} className="hidden" />
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleFileUpload}
        className="hidden"
      />

      <main className="flex-1 flex flex-col relative w-full pt-16 pb-safe bg-surface">
        <div className="flex flex-col w-full relative">

          {/* ── Viewfinder Viewport Container ── */}
          <div className="relative w-full aspect-[3/4] max-h-[66vh] bg-inverse-surface rounded-xl overflow-hidden flex flex-col justify-between p-space-md shadow-xl mx-auto">
            {/* Live Camera Video Stream */}
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="absolute inset-0 w-full h-full object-cover brightness-95"
            />

            {/* Dark Vignette Overlay */}
            <div className="absolute inset-0 bg-gradient-to-b from-inverse-surface/80 via-transparent to-inverse-surface/90 pointer-events-none" />

            {/* Top Guidance & Quality Indicators */}
            <div className="relative z-10 flex flex-col items-center gap-space-xs w-full pt-space-xs">
              <div className="bg-inverse-surface/90 backdrop-blur-md px-space-md py-1.5 rounded-full flex items-center gap-space-xs shadow-md">
                <span className="material-symbols-outlined text-primary-fixed text-[18px]">document_scanner</span>
                <span className="font-label-md text-label-md text-inverse-on-surface">
                  {t('sc_guide')}
                </span>
              </div>

              <div className="flex items-center gap-space-xs bg-inverse-surface/70 backdrop-blur-sm px-space-sm py-1 rounded-full">
                <span className="w-2 h-2 rounded-full bg-primary-fixed animate-pulse" />
                <span className="font-label-sm text-label-sm text-inverse-on-surface">{t('sc_quality')}</span>
                <span className="text-outline-variant opacity-60">•</span>
                <span className="material-symbols-outlined text-primary-fixed text-[14px]">auto_fix_high</span>
        <span className="font-label-sm text-label-sm text-primary-fixed font-bold">{t('sc_preview_only')}</span>
              </div>
            </div>

            {/* Document Frame Guide Overlay (Adaptive Viewfinder) */}
            <div className="relative z-10 mx-auto w-full max-w-[280px] h-[58%] my-auto flex items-center justify-center">
              <div className="absolute inset-0 bg-primary/10 rounded-xl transition-all duration-300 pointer-events-none" />
              {/* Animated Scan Line Beam */}
              <div className="absolute inset-x-0 h-1 bg-gradient-to-r from-transparent via-primary-fixed to-transparent opacity-80 blur-[0.5px] animate-[bounce_2.5s_infinite]" />

              {/* 4 L-Corners */}
              <div className="absolute top-0 right-0 w-7 h-7 flex flex-col items-end justify-start">
                <div className="w-full h-1.5 bg-primary-fixed rounded-full shadow-[0_0_8px_rgba(165,243,204,0.8)]" />
                <div className="w-1.5 h-full bg-primary-fixed rounded-full shadow-[0_0_8px_rgba(165,243,204,0.8)]" />
              </div>
              <div className="absolute top-0 left-0 w-7 h-7 flex flex-col items-start justify-start">
                <div className="w-full h-1.5 bg-primary-fixed rounded-full shadow-[0_0_8px_rgba(165,243,204,0.8)]" />
                <div className="w-1.5 h-full bg-primary-fixed rounded-full shadow-[0_0_8px_rgba(165,243,204,0.8)]" />
              </div>
              <div className="absolute bottom-0 right-0 w-7 h-7 flex flex-col items-end justify-end">
                <div className="w-1.5 h-full bg-primary-fixed rounded-full shadow-[0_0_8px_rgba(165,243,204,0.8)]" />
                <div className="w-full h-1.5 bg-primary-fixed rounded-full shadow-[0_0_8px_rgba(165,243,204,0.8)]" />
              </div>
              <div className="absolute bottom-0 left-0 w-7 h-7 flex flex-col items-start justify-end">
                <div className="w-1.5 h-full bg-primary-fixed rounded-full shadow-[0_0_8px_rgba(165,243,204,0.8)]" />
                <div className="w-full h-1.5 bg-primary-fixed rounded-full shadow-[0_0_8px_rgba(165,243,204,0.8)]" />
              </div>

              {/* Center Target Ring */}
              <div className="w-10 h-10 rounded-full border border-primary-fixed/40 flex items-center justify-center">
                <div className="w-2 h-2 rounded-full bg-primary-fixed shadow-[0_0_6px_rgba(165,243,204,1)]" />
              </div>
            </div>

            {/* Alignment Tips Footer */}
            <div className="relative z-10 flex items-center justify-between text-inverse-on-surface px-space-xs pb-space-xs">
              <div className="flex items-center gap-1.5 bg-inverse-surface/80 px-2.5 py-1 rounded-lg">
                <span className="material-symbols-outlined text-[16px] text-primary-fixed">fit_screen</span>
                <span className="font-label-sm text-label-sm">{t('sc_recognition_unavailable')}</span>
              </div>
              <div className="flex items-center gap-1.5 bg-inverse-surface/80 px-2.5 py-1 rounded-lg">
                <span className="font-label-sm text-label-sm text-secondary-fixed">{docTags[docType]}</span>
              </div>
            </div>
          </div>

          {/* ── Thumb-Zone Controls & Operational Trays ── */}
          <div className="w-full px-margin-mobile pt-space-md pb-space-lg flex flex-col gap-space-md">

            {/* Segmented Document Type Selector (Tabs) */}
            <div className="w-full bg-surface-container p-1 rounded-full flex items-center justify-between shadow-sm">
              <button
                type="button"
                onClick={() => setDocType('prescription')}
                className={`flex-1 py-2 px-space-sm rounded-full font-label-md text-label-md transition-all duration-200 flex items-center justify-center gap-1 ${
                  docType === 'prescription' ? 'bg-primary text-on-primary shadow-sm' : 'text-on-surface-variant'
                }`}
              >
                <span className="material-symbols-outlined text-[16px]">prescriptions</span>
                <span>{t('sc_tab_rx')}</span>
              </button>
              <button
                type="button"
                onClick={() => setDocType('invoice')}
                className={`flex-1 py-2 px-space-sm rounded-full font-label-md text-label-md transition-all duration-200 flex items-center justify-center gap-1 ${
                  docType === 'invoice' ? 'bg-primary text-on-primary shadow-sm' : 'text-on-surface-variant'
                }`}
              >
                <span className="material-symbols-outlined text-[16px]">receipt_long</span>
                <span>{t('sc_tab_invoice')}</span>
              </button>
              <button
                type="button"
                onClick={() => setDocType('receipt')}
                className={`flex-1 py-2 px-space-sm rounded-full font-label-md text-label-md transition-all duration-200 flex items-center justify-center gap-1 ${
                  docType === 'receipt' ? 'bg-primary text-on-primary shadow-sm' : 'text-on-surface-variant'
                }`}
              >
                <span className="material-symbols-outlined text-[16px]">payments</span>
                <span>{t('sc_tab_receipt')}</span>
              </button>
            </div>

            {/* Shutter Trigger Bar (One-Handed Physical Arc) */}
            <div className="w-full flex items-center justify-around pt-space-xs">
              {/* Gallery Import Target */}
              <button
                type="button"
                aria-label={t('sc_choose_image')}
                onClick={() => fileInputRef.current?.click()}
                className="w-touch-target-min h-touch-target-min rounded-full bg-surface-container-high text-on-surface flex flex-col items-center justify-center gap-0.5 active:scale-95 transition-transform"
              >
                <span className="material-symbols-outlined text-[24px]">photo_library</span>
                <span className="font-label-sm text-[10px] leading-none">{t('sc_photos')}</span>
              </button>

              {/* Big Shutter Trigger Button */}
              <button
                type="button"
                aria-label={t('sc_capture')}
                onClick={handleCapture}
                className="w-20 h-20 rounded-full bg-surface-container p-1 shadow-lg flex items-center justify-center active:scale-95 transition-transform group"
              >
                <div className="w-full h-full rounded-full bg-primary flex items-center justify-center group-hover:bg-primary-container transition-colors shadow-md">
                  <div className="w-14 h-14 rounded-full bg-surface-container-lowest flex items-center justify-center">
                    <span className="material-symbols-outlined text-primary text-[30px] icon-filled">
                      camera
                    </span>
                  </div>
                </div>
              </button>

              {/* Flash / Torch Toggle */}
              <button
                type="button"
                aria-label={t('sc_toggle_torch')}
                onClick={toggleTorch}
                className="w-touch-target-min h-touch-target-min rounded-full bg-surface-container-high text-on-surface flex flex-col items-center justify-center gap-0.5 active:scale-95 transition-transform"
              >
                <span className="material-symbols-outlined text-[24px]">
                  {isTorchOn ? 'flashlight_off' : 'flashlight_on'}
                </span>
                <span className="font-label-sm text-[10px] leading-none">
                  {isTorchOn ? t('sc_off') : t('sc_torch')}
                </span>
              </button>
            </div>

            {/* Pharmacist Tip Card */}
            <div className="w-full bg-surface-container-low rounded-xl p-space-sm flex items-center gap-space-sm">
              <div className="w-8 h-8 rounded-full bg-primary-fixed flex items-center justify-center flex-shrink-0">
                <span className="material-symbols-outlined text-primary text-[18px]">verified</span>
              </div>
              <div className="flex flex-col min-w-0">
                <span className="font-label-md text-label-md text-on-surface font-bold">
                  {t('sc_extract_unavailable')}
                </span>
                <span className="font-body-sm text-body-sm text-on-surface-variant truncate">
                  {t('sc_manual_hint')}
                </span>
              </div>
            </div>

          </div>

          {/* ── Post-Capture Photo Review Tray (Sliding up from bottom) ── */}
          {isTrayOpen && (
            <div className="fixed inset-x-0 bottom-0 z-50 p-margin-mobile bg-surface-container-lowest shadow-[0_-6px_24px_rgba(16,30,24,0.12)] rounded-t-2xl transition-all duration-300 flex flex-col gap-space-md">
              <div className="w-12 h-1 bg-surface-container-high rounded-full mx-auto" />

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-space-sm">
                  <div className="w-10 h-10 rounded-full bg-primary-fixed flex items-center justify-center">
                    <span className="material-symbols-outlined text-primary text-[22px]">task_alt</span>
                  </div>
                  <div className="flex flex-col">
                    <h2 className="font-headline-sm text-headline-sm text-on-surface">{t('sc_img_captured')}</h2>
                    <span className="font-body-sm text-body-sm text-on-surface-variant">{t('sc_tray_hint')}</span>
                  </div>
                </div>
                <span className="px-2.5 py-1 rounded-full bg-primary-fixed font-label-sm text-label-sm text-primary font-bold">
                  {t('sc_ocr_unavailable')}
                </span>
              </div>

              {/* Scanned Thumbnail Preview */}
              <div className="w-full bg-surface-container-low p-space-sm rounded-xl flex items-center justify-between">
                <div className="flex items-center gap-space-sm">
                  {capturedImage ? (
                    <img
                      src={capturedImage}
                      alt={t('sc_image_alt')}
                      className="w-12 h-12 rounded-lg object-cover flex-shrink-0 border border-outline-variant"
                    />
                  ) : (
                    <div className="w-12 h-12 rounded-lg bg-surface-container-highest flex items-center justify-center">
                      <span className="material-symbols-outlined text-primary">image</span>
                    </div>
                  )}
                  <div className="flex flex-col min-w-0">
                    <span className="font-label-lg text-label-lg text-on-surface font-bold truncate">
                      {docNames[docType]}
                    </span>
                    <span className="font-body-sm text-body-sm text-on-surface-variant">{t('sc_local_only')}</span>
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex flex-col gap-space-xs w-full pt-space-xs pb-safe">
                <button
                  type="button"
                  disabled
                  className="w-full h-14 bg-secondary text-on-secondary rounded-lg font-label-lg text-label-lg flex items-center justify-center gap-space-sm shadow-md active:opacity-90 transition-opacity disabled:opacity-50"
                >
                  <span className="material-symbols-outlined text-[22px]">smart_toy</span>
                  <span>{t('sc_extract_btn')}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setIsTrayOpen(false)}
                  className="w-full h-12 bg-surface-container-high text-on-surface rounded-lg font-label-lg text-label-lg flex items-center justify-center gap-space-xs active:bg-surface-container transition-colors"
                >
                  <span className="material-symbols-outlined text-[20px]">replay</span>
                  <span>{t('sc_capture_another')}</span>
                </button>
              </div>
            </div>
          )}

          {/* Toast Notification */}
          {toast && (
            <div className="fixed top-20 left-1/2 -translate-x-1/2 z-50 bg-inverse-surface text-inverse-on-surface px-space-md py-2 rounded-full font-label-md text-label-md flex items-center gap-2 shadow-lg transition-all">
              <span className="material-symbols-outlined text-primary-fixed text-[18px]">
                {toast.icon}
              </span>
              <span>{toast.message}</span>
            </div>
          )}

        </div>
      </main>
    </div>
  );
}