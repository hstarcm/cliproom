import { useEffect, useState } from "react";
import QRCode from "qrcode";

export interface QrModalProps {
  shareUrl: string;
  onClose: () => void;
}

/** Big, obvious QR popup for a room's share link (operator dashboard). */
export default function QrModal({ shareUrl, onClose }: QrModalProps) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    QRCode.toDataURL(shareUrl, { width: 340, margin: 2 })
      .then((url) => alive && setDataUrl(url))
      .catch(() => alive && setDataUrl(null));
    return () => {
      alive = false;
    };
  }, [shareUrl]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — user can select the text manually */
    }
  };

  return (
    <div
      className="modal-overlay"
      data-testid="qr-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-card" role="dialog" aria-label="Room share QR code">
        <h3 style={{ margin: "0 0 10px" }}>Room share link</h3>
        {dataUrl ? (
          <img
            src={dataUrl}
            alt="QR code of the room share link"
            width={340}
            height={340}
            data-testid="qr-image"
            style={{ borderRadius: 8, border: "1px solid #e1e4e8" }}
          />
        ) : (
          <p className="error">QR unavailable</p>
        )}
        <p className="share-url" data-testid="qr-url" style={{ margin: "12px 0" }}>
          {shareUrl}
        </p>
        <p style={{ margin: "0", display: "flex", gap: 8, justifyContent: "center" }}>
          <button className="primary" onClick={copy}>
            {copied ? "Copied ✓" : "Copy link"}
          </button>
          <button onClick={onClose}>Close</button>
        </p>
      </div>
    </div>
  );
}
