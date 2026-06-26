import { useQuery } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { ArrowUpRight, ArrowDownRight, Activity } from "lucide-react";

export default function ROIReportPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["roi_report"],
    queryFn: async () => {
      const res = await fetch("/api/reports/roi");
      if (!res.ok) throw new Error("Failed to fetch ROI stats");
      return res.json();
    }
  });

  if (isLoading) return <div className="p-8 text-center text-slate-400">Loading ROI stats...</div>;
  if (error) return <div className="p-8 text-center text-red-400">Error loading report</div>;

  const { overall, monthly } = data;

  const formatMoney = (val: number) => new Intl.NumberFormat('ko-KR').format(val) + '원';
  const calculateROI = (ret: number, inv: number) => inv > 0 ? (((ret - inv) / inv) * 100).toFixed(2) : "0.00";

  // Prepare chart data
  const chartData = monthly.map((m: any) => ({
    name: m.month,
    WIN: parseFloat(calculateROI(m.stats.WIN.return, m.stats.WIN.investment)),
    QUINELLA: parseFloat(calculateROI(m.stats.QUINELLA.return, m.stats.QUINELLA.investment)),
    TRIO: parseFloat(calculateROI(m.stats.TRIO.return, m.stats.TRIO.investment)),
  }));

  const StrategyCard = ({ title, stats, color }: { title: string, stats: any, color: string }) => {
    const roi = parseFloat(calculateROI(stats.return, stats.investment));
    const isPositive = roi >= 0;
    
    return (
      <div className="relative overflow-hidden bg-white/5 border border-white/10 rounded-2xl p-6 shadow-xl backdrop-blur-md transition-all hover:bg-white/10">
        <div className={`absolute top-0 left-0 w-full h-1 bg-${color}-500`}></div>
        <div className="flex justify-between items-start mb-4">
          <h3 className="text-xl font-bold text-slate-100">{title}</h3>
          <div className={`flex items-center gap-1 text-sm font-bold px-2 py-1 rounded-md ${isPositive ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
            {isPositive ? <ArrowUpRight size={16}/> : <ArrowDownRight size={16}/>}
            {isPositive ? '+' : ''}{roi}%
          </div>
        </div>
        
        <div className="space-y-3">
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">총 투자금</span>
            <span className="text-slate-200 font-medium">{formatMoney(stats.investment)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">총 회수금</span>
            <span className={`${isPositive ? 'text-emerald-400' : 'text-rose-400'} font-bold`}>{formatMoney(stats.return)}</span>
          </div>
          <div className="w-full h-px bg-white/10 my-2"></div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">적중 횟수</span>
            <span className="text-indigo-300 font-medium">{stats.hits} / {stats.total_races}경기</span>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="max-w-7xl mx-auto min-h-screen bg-slate-950 text-slate-200 p-4 md:p-8">
      <header className="mb-10">
        <h1 className="text-3xl font-extrabold bg-gradient-to-r from-emerald-400 via-teal-400 to-indigo-400 bg-clip-text text-transparent flex items-center gap-3">
          <Activity className="text-emerald-400" size={32} />
          ROI 분석 대시보드
        </h1>
        <p className="text-slate-400 mt-2">전체 AI 예측 모델의 승식별 백테스트 수익률 결과</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
        <StrategyCard title="단승식 (WIN)" stats={overall.WIN} color="indigo" />
        <StrategyCard title="복승식 (QUINELLA)" stats={overall.QUINELLA} color="purple" />
        <StrategyCard title="삼복승식 (TRIO)" stats={overall.TRIO} color="pink" />
      </div>

      <div className="bg-white/5 border border-white/10 rounded-3xl p-6 shadow-2xl backdrop-blur-md">
        <h2 className="text-xl font-bold text-slate-100 mb-6 flex items-center gap-2">
          📈 월별 수익률 추이 (ROI %)
        </h2>
        <div className="h-[400px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff1a" />
              <XAxis dataKey="name" stroke="#94a3b8" />
              <YAxis stroke="#94a3b8" tickFormatter={(val) => `${val}%`} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }}
                itemStyle={{ fontWeight: 'bold' }}
              />
              <Legend />
              <Line type="monotone" dataKey="WIN" name="단승식" stroke="#6366f1" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
              <Line type="monotone" dataKey="QUINELLA" name="복승식" stroke="#a855f7" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
              <Line type="monotone" dataKey="TRIO" name="삼복승식" stroke="#ec4899" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
