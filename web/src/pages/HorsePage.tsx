import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { LineChart, Line, ResponsiveContainer, YAxis } from "recharts";
import { useTranslation } from "../hooks/useTranslation";

const mockRecentForm = [
  { race: 1, finish: 5 },
  { race: 2, finish: 2 },
  { race: 3, finish: 1 },
  { race: 4, finish: 4 },
  { race: 5, finish: 1 },
];

export default function HorsePage() {
  const { horseId } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <div className="max-w-md mx-auto min-h-screen bg-gray-50">
      <header className="bg-slate-900 text-white p-4 sticky top-0 z-10 shadow-md">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)}><ArrowLeft size={20}/></button>
          <h1 className="text-xl font-bold">{t("horse.name")} {horseId}</h1>
        </div>
      </header>
      
      <div className="p-4 space-y-4">
        <div className="bg-white p-6 rounded-xl shadow-sm border text-center relative">
          <div className="absolute top-4 right-4 text-yellow-500">
            ★ {/* Favorites star */}
          </div>
          <div className="w-20 h-20 bg-gray-200 rounded-full mx-auto mb-4 flex items-center justify-center text-gray-400">
            IMG
          </div>
          <h2 className="text-2xl font-bold mb-1">Mock Horse Name</h2>
          <p className="text-gray-500 text-sm">{t("horse.age_sex")}: 4 • Sex: M</p>
          <div className="mt-2 text-xs text-gray-400">
            Sire: Mock Sire × Dam: Mock Dam
          </div>
        </div>
        
        <div className="bg-white p-4 rounded-xl shadow-sm border">
          <h3 className="font-bold text-lg mb-4">Recent Form (Sparkline)</h3>
          <div className="h-32 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={mockRecentForm}>
                <YAxis reversed domain={[1, 14]} hide />
                <Line 
                  type="monotone" 
                  dataKey="finish" 
                  stroke="#3b82f6" 
                  strokeWidth={3} 
                  dot={{ r: 4, fill: "#3b82f6" }} 
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-between text-xs text-gray-400 mt-2">
            <span>Older</span>
            <span>Newer</span>
          </div>
        </div>
      </div>
    </div>
  );
}
