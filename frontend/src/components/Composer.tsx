import { useRef, useState } from "react";

export interface ComposerProps {
  onAddText: (content: string) => Promise<void>;
  onUpload: (file: File) => Promise<void>;
}

export default function Composer({ onAddText, onUpload }: ComposerProps) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const addText = async () => {
    const content = text;
    if (content.length < 1 || content.length > 10_000) {
      setError("Clip must be 1–10,000 characters.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onAddText(content);
      setText("");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const upload = async () => {
    const file = fileInput.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await onUpload(file);
      if (fileInput.current) fileInput.current.value = "";
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" data-testid="composer">
      <textarea
        rows={3}
        placeholder="Share a text clip… (1–10,000 characters)"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
        <button className="primary" onClick={addText} disabled={busy}>
          Add clip
        </button>
        <input ref={fileInput} type="file" aria-label="Upload file" />
        <button onClick={upload} disabled={busy}>
          Upload
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
