import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { IconCheck } from "./icons";

const ToastCtx = createContext<(msg: string) => void>(() => {});

export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [msg, setMsg] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const toast = useCallback((m: string) => {
    setMsg(m);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setMsg(null), 2000);
  }, []);

  return (
    <ToastCtx.Provider value={toast}>
      {children}
      {msg !== null && (
        <div className="animate-toast-in fixed bottom-[26px] left-1/2 z-50 flex -translate-x-1/2 items-center gap-[9px] rounded-[9px] bg-toast-bg px-[18px] py-[10px] text-[12.5px] font-medium text-white shadow-[0_8px_24px_rgba(0,0,0,.35)]">
          <span className="text-[#19D27C]">
            <IconCheck size={15} />
          </span>
          {msg}
        </div>
      )}
    </ToastCtx.Provider>
  );
}
