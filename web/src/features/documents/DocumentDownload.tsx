import * as React from "react";
import { toast } from "sonner";
import { downloadDocument } from "@/lib/local/routes";

/** Saves a copy of a document from the documents folder (or browser storage) through the browser's download. */
export function DocumentDownload({
  id,
  className,
  children,
  onDownloaded,
  ...props
}: {
  id: number;
  className?: string;
  children: React.ReactNode;
  onDownloaded?: () => void;
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "onClick" | "id">) {
  return (
    <button
      type="button"
      className={className}
      onClick={async () => {
        try {
          await downloadDocument(id);
          onDownloaded?.();
        } catch (error) {
          toast.error("The file could not be downloaded", { description: (error as Error).message });
        }
      }}
      {...props}
    >
      {children}
    </button>
  );
}
