import { UploadCloud } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

/** Drag-and-drop or click-to-browse file input with a size check. */
export function Dropzone({
  accept,
  label,
  hint,
  maxBytes = 50 * 1024 * 1024,
  onFile,
  disabled,
}: {
  accept: string;
  label: string;
  hint: string;
  maxBytes?: number;
  onFile: (file: File) => void;
  disabled?: boolean;
}) {
  const input = React.useRef<HTMLInputElement>(null);
  const [over, setOver] = React.useState(false);
  const [error, setError] = React.useState("");
  const extensions = accept.split(",").map((e) => e.trim().toLowerCase());

  const take = (file?: File) => {
    if (!file) return;
    const name = file.name.toLowerCase();
    if (!extensions.some((ext) => name.endsWith(ext))) {
      setError(`Choose a ${extensions.join(" or ")} file.`);
      return;
    }
    if (file.size > maxBytes) {
      setError(`The file is larger than ${Math.round(maxBytes / 1024 / 1024)} MB.`);
      return;
    }
    setError("");
    onFile(file);
  };

  return (
    <div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          take(event.dataTransfer.files[0]);
        }}
        className={cn(
          "flex w-full flex-col items-center gap-2 rounded-lg border-2 border-dashed p-6 text-center transition-colors duration-150 hover:border-primary/60 hover:bg-accent/40 disabled:opacity-50",
          over && "border-primary bg-accent",
        )}
      >
        <UploadCloud className="size-6 text-muted-foreground" aria-hidden />
        <span className="font-medium">{label}</span>
        <span className="text-caption text-muted-foreground">{hint}</span>
      </button>
      <input
        ref={input}
        type="file"
        accept={accept}
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(event) => {
          take(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
      {error && (
        <p className="mt-1 text-caption text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
