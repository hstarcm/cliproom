import { useRef, useState } from "react";

export interface ComposerProps {
  onAddText: (content: string) => Promise<void>;
  onUpload: (file: File) => Promise<void>;
  maxFileMb?: number;
}

export const ACCEPTED_EXTENSIONS =
  ".png,.jpg,.jpeg,.gif,.webp,.pdf,.txt,.md,.csv,.zip,.7z,.rar," +
  ".py,.ipynb,.yaml,.yml,.json,.toml,.ini,.xml,.sql," +
  ".js,.mjs,.cjs,.ts,.tsx,.jsx,.css,.scss,.less,.vue,.svelte," +
  ".java,.c,.h,.hpp,.cc,.cpp,.cs,.go,.rs,.rb,.kt,.swift,.sh,.bash," +
  ".doc,.docx,.xls,.xlsx,.ppt,.pptx";

export default function Composer({ onAddText, onUpload, maxFileMb = 10 }: ComposerProps) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
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
    if (!file) {
      setError("Choose a file first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onUpload(file);
      if (fileInput.current) fileInput.current.value = "";
      setFileName(null);
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
      <p style={{ margin: "8px 0 0" }}>
        <button className="primary" onClick={addText} disabled={busy}>
          Add clip
        </button>
      </p>

      <div className="upload-box" data-testid="upload-box">
        <span className="upload-box-title">📎 Attach a file</span>
        <label className="file-label">
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPTED_EXTENSIONS}
            aria-label="Choose file to upload"
            onChange={(e) => setFileName(e.target.files?.[0]?.name ?? null)}
          />
          {fileName ?? "Choose file…"}
        </label>
        <button className="upload-btn" onClick={upload} disabled={busy}>
          Upload
        </button>
        <span className="muted">
          up to {maxFileMb} MB · images, docs &amp; Office, code &amp; config files,
          archives (zip/7z/rar) · executables, HTML/SVG and macro-enabled
          Office files are rejected
        </span>
        {fileName && <span className="muted">selected: {fileName}</span>}
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
