import { useNavigate, useLocation } from "react-router-dom";
import { Home, Star, BarChart2 } from "lucide-react";

const tabs = [
  { label: "홈", icon: Home, path: "/races" },
  { label: "즐겨찾기", icon: Star, path: "/favorites" },
  { label: "ROI 리포트", icon: BarChart2, path: "/reports/roi" },
];

export function BottomNav() {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-30 bg-slate-950/90 backdrop-blur-md border-t border-white/10 safe-area-pb">
      <div className="max-w-7xl mx-auto flex">
        {tabs.map(({ label, icon: Icon, path }) => {
          const active = pathname.startsWith(path);
          return (
            <button
              key={path}
              onClick={() => navigate(path)}
              className={`flex-1 flex flex-col items-center gap-1 py-3 text-[11px] font-semibold transition-colors ${
                active ? "text-indigo-400" : "text-slate-500 hover:text-slate-300"
              }`}
            >
              <Icon size={22} strokeWidth={active ? 2.5 : 1.8} />
              {label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
