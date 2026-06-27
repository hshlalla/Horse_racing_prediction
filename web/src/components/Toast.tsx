import { useEffect, useState } from "react";
import { CheckCircle, XCircle, Info } from "lucide-react";

export type ToastType = "success" | "error" | "info";

export interface ToastProps {
  message: string;
  type?: ToastType;
  duration?: number;
  onClose: () => void;
}

export function Toast({ message, type = "info", duration = 3000, onClose }: ToastProps) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    // Small delay to trigger entry animation
    requestAnimationFrame(() => setIsVisible(true));
    
    const timer = setTimeout(() => {
      setIsVisible(false);
      setTimeout(onClose, 300); // Wait for exit animation
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onClose]);

  const icons = {
    success: <CheckCircle className="text-emerald-400" size={20} />,
    error: <XCircle className="text-rose-400" size={20} />,
    info: <Info className="text-indigo-400" size={20} />,
  };

  const bgColors = {
    success: "bg-emerald-900/80 border-emerald-500/50",
    error: "bg-rose-900/80 border-rose-500/50",
    info: "bg-indigo-900/80 border-indigo-500/50",
  };

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[100] pointer-events-none">
      <div 
        className={`flex items-center gap-3 px-5 py-3.5 rounded-full border backdrop-blur-xl shadow-2xl transition-all duration-300 ease-out
          ${bgColors[type]}
          ${isVisible ? 'translate-y-0 opacity-100 scale-100' : 'translate-y-10 opacity-0 scale-95'}
        `}
      >
        {icons[type]}
        <span className="font-bold tracking-wide text-white text-sm whitespace-nowrap">{message}</span>
      </div>
    </div>
  );
}
