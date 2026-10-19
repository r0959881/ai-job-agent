/* `const confirm = useConfirm(); if (await confirm({...})) …` — an accessible confirmation dialog. */
import * as React from "react";
import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/primitives";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from "@/components/ui/overlays";

export interface ConfirmOptions {
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  destructive?: boolean;
  /** When set, the user must type this text before confirming. */
  typeToConfirm?: string;
}

type Resolver = (value: boolean) => void;
const ConfirmContext = React.createContext<((options: ConfirmOptions) => Promise<boolean>) | null>(null);

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [options, setOptions] = React.useState<ConfirmOptions | null>(null);
  const [typed, setTyped] = React.useState("");
  const resolver = React.useRef<Resolver | null>(null);

  const confirm = React.useCallback((next: ConfirmOptions) => {
    setTyped("");
    setOptions(next);
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  const close = (value: boolean) => {
    resolver.current?.(value);
    resolver.current = null;
    setOptions(null);
  };

  const blocked = Boolean(options?.typeToConfirm) && typed !== options?.typeToConfirm;

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <AlertDialog open={Boolean(options)} onOpenChange={(open) => !open && close(false)}>
        <AlertDialogContent>
          <div className="space-y-2">
            <AlertDialogTitle>{options?.title}</AlertDialogTitle>
            {options?.description && <AlertDialogDescription asChild><div>{options.description}</div></AlertDialogDescription>}
          </div>
          {options?.typeToConfirm && (
            <div className="space-y-1.5">
              <label htmlFor="confirm-type" className="text-body">
                Type <span className="font-mono font-semibold">{options.typeToConfirm}</span> to confirm
              </label>
              <Input id="confirm-type" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} />
            </div>
          )}
          <div className="flex justify-end gap-2">
            <AlertDialogCancel onClick={() => close(false)}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={blocked}
              className={buttonVariants({ variant: options?.destructive ? "danger" : "default" })}
              onClick={(event) => {
                if (blocked) {
                  event.preventDefault();
                  return;
                }
                close(true);
              }}
            >
              {options?.confirmLabel ?? "Confirm"}
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const confirm = React.useContext(ConfirmContext);
  if (!confirm) throw new Error("useConfirm must be used inside ConfirmProvider");
  return confirm;
}
