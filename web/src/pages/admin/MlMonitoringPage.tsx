import { useQuery } from "@tanstack/react-query";
import { fetchMlStatus } from "../../api/admin";
import type { TrackModelInfo } from "../../api/admin";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

function TrackCard({ info }: { info: TrackModelInfo }) {
  const hasModel = info.model_version !== null;
  return (
    <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
      <div className="flex justify-between items-center mb-3">
        <span className="font-bold text-slate-100 text-lg">{info.track}</span>
        <span
          className={`text-xs px-2 py-1 rounded-full font-medium ${
            hasModel
              ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
              : "bg-slate-700 text-slate-400 border border-slate-600"
          }`}
        >
          {hasModel ? info.model_version : "No model"}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="bg-slate-900/50 rounded-xl p-3">
          <div className="text-slate-500 text-xs mb-1">Val Log-Loss</div>
          <div className="font-mono text-slate-200 font-bold">
            {info.log_loss !== null ? info.log_loss.toFixed(4) : "—"}
          </div>
        </div>
        <div className="bg-slate-900/50 rounded-xl p-3">
          <div className="text-slate-500 text-xs mb-1">Val ROI</div>
          <div
            className={`font-mono font-bold ${
              info.roi !== null && info.roi >= 0 ? "text-emerald-400" : "text-red-400"
            }`}
          >
            {info.roi !== null ? `${(info.roi * 100).toFixed(1)}%` : "—"}
          </div>
        </div>
      </div>
      {info.promoted_at && (
        <div className="text-xs text-slate-500 mt-3">
          Promoted: {new Date(info.promoted_at).toLocaleString("ko-KR")}
        </div>
      )}
    </div>
  );
}

const CHART_COLORS = ["#6366f1", "#8b5cf6", "#a78bfa"];

export default function MlMonitoringPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["admin", "ml", "status"],
    queryFn: fetchMlStatus,
    refetchInterval: 60_000,
  });

  const chartData =
    data?.tracks
      .filter((t) => t.log_loss !== null)
      .map((t) => ({ track: t.track, log_loss: t.log_loss as number })) ?? [];

  return (
    <div className="max-w-2xl mx-auto min-h-screen bg-slate-950 text-slate-200 p-4">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-slate-100">ML 모니터링</h1>
        <button
          onClick={() => refetch()}
          className="text-xs bg-white/10 border border-white/10 rounded-lg px-3 py-1.5 hover:bg-white/20 transition-colors"
        >
          새로고침
        </button>
      </div>

      {isLoading && (
        <div className="text-slate-500 text-center mt-10">Loading...</div>
      )}

      {error && (
        <div className="text-red-400 bg-red-500/10 border border-red-500/30 rounded-xl p-4">
          Failed to load ML status. Check that you are logged in as admin.
        </div>
      )}

      {data && (
        <>
          {/* Model Status Cards */}
          <section className="mb-8">
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
              Model Status
            </h2>
            <div className="grid gap-4">
              {data.tracks.map((t) => (
                <TrackCard key={t.track} info={t} />
              ))}
            </div>
          </section>

          {/* Performance Chart */}
          {chartData.length > 0 && (
            <section className="mb-6">
              <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
                Performance Chart — Log-Loss per Track
              </h2>
              <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart
                    data={chartData}
                    margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="rgba(255,255,255,0.06)"
                    />
                    <XAxis
                      dataKey="track"
                      tick={{ fill: "#94a3b8", fontSize: 12 }}
                      axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: "#94a3b8", fontSize: 11 }}
                      axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
                      tickLine={false}
                      domain={[0, "auto"]}
                      width={40}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#0f172a",
                        border: "1px solid rgba(255,255,255,0.1)",
                        borderRadius: "0.75rem",
                        color: "#e2e8f0",
                        fontSize: 12,
                      }}
                      formatter={(value: number) => [value.toFixed(4), "Log-Loss"]}
                    />
                    <Bar dataKey="log_loss" radius={[6, 6, 0, 0]}>
                      {chartData.map((_, i) => (
                        <Cell
                          key={i}
                          fill={CHART_COLORS[i % CHART_COLORS.length]}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          )}

          <div className="text-xs text-slate-600 text-right">
            Last updated:{" "}
            {new Date(data.last_updated).toLocaleString("ko-KR")}
          </div>
        </>
      )}
    </div>
  );
}
