import * as React from "react";

/** Shows a PDF (a Blob, or base64 bytes from the server) in the browser's own PDF viewer. */
export function PdfFrame({
  blob,
  base64,
  title,
  className,
}: {
  blob?: Blob | null;
  base64?: string | null;
  title: string;
  className?: string;
}) {
  const [url, setUrl] = React.useState("");
  React.useEffect(() => {
    let source = blob ?? null;
    if (!source && base64) {
      const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
      source = new Blob([bytes], { type: "application/pdf" });
    }
    if (!source) return;
    const next = URL.createObjectURL(source.type ? source : new Blob([source], { type: "application/pdf" }));
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [blob, base64]);
  if (!url) return null;
  return (
    <iframe
      title={title}
      src={`${url}#toolbar=1&view=FitH`}
      className={className ?? "h-[70vh] w-full rounded-md border bg-card"}
    />
  );
}
