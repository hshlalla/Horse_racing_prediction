import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchRaces } from "../api/races";
import { format } from "date-fns";
import { parseRaceTime } from "../lib/time";

const TRACK_ORDER = ["SEOUL", "BUSAN", "JEJU"];
const TRACK_LABEL: Record<string, string> = { SEOUL: "서울", BUSAN: "부산", JEJU: "제주" };
const TRACK_COLOR: Record<string, string> = {
  SEOUL: "text-indigo-300 bg-indigo-500/20 border-indigo-500/30",
  BUSAN: "text-teal-300 bg-teal-500/20 border-teal-500/30",
  JEJU: "text-amber-300 bg-amber-500/20 border-amber-500/30",
};
const TRACK_SECTION: Record<string, string> = {
  SEOUL: "border-indigo-500/20",
  BUSAN: "border-teal-500/20",
  JEJU: "border-amber-500/20",
};

function getRaceStatus(postTime: string | null | undefined, completed?: boolean) {
  // 결과가 DB에 있으면 무조건 완료
  if (completed) return { label: "완료", cls: "bg-white/5 text-slate-500 border-white/10" };
  if (!postTime) return null;
  const now = new Date();
  const start = parseRaceTime(postTime);
  if (!start) return null;
  const diffMin = (now.getTime() - start.getTime()) / 60000;
  if (diffMin < -1) return { label: "예정", cls: "bg-slate-700/60 text-slate-300 border-slate-600/40" };
  if (diffMin < 30) return { label: "진행중", cls: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30 animate-pulse" };
  return { label: "완료", cls: "bg-white/5 text-slate-500 border-white/10" };
}

export default function HomePage() {
  const { date } = useParams();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["races", date],
    queryFn: () => fetchRaces(date!),
    enabled: !!date,
    refetchInterval: 60000,
  });

  const grouped = TRACK_ORDER.reduce<Record<string, any[]>>((acc, track) => {
    acc[track] = (data?.items ?? []).filter((r: any) => r.track === track)
      .sort((a: any, b: any) => {
        if (!a.post_time) return 1;
        if (!b.post_time) return -1;
        return (parseRaceTime(a.post_time)?.getTime() ?? 0) - (parseRaceTime(b.post_time)?.getTime() ?? 0);
      });
    return acc;
  }, {});

  const totalRaces = data?.items?.length ?? 0;

  return (
    <div className="max-w-7xl mx-auto min-h-screen bg-slate-950 text-slate-200 pb-24">
      <header className="p-4 border-b border-white/10 flex justify-between items-center sticky top-0 bg-slate-950/90 backdrop-blur-md z-10 shadow-lg shadow-black/20">
        <h1 className="text-xl font-bold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
          KRA Quant
        </h1>
        <input
          type="date"
          value={date}
          onChange={(e) => navigate(`/races/${e.target.value}`)}
          className="bg-white/5 border border-white/10 rounded-lg p-1.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all text-slate-300 [color-scheme:dark]"
        />
      </header>

      {isLoading ? (
        <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-28 bg-white/5 rounded-2xl border border-white/5 animate-pulse" />
          ))}
        </div>
      ) : totalRaces === 0 ? (
        <div className="flex flex-col items-center justify-center mt-32 gap-4 text-center px-8">
          <span className="text-5xl">🏇</span>
          <p className="text-lg font-semibold text-slate-300">{date} 경주 없음</p>
          <p className="text-sm text-slate-500">다른 날짜를 선택해 주세요.</p>
        </div>
      ) : (
        <div className="p-4 space-y-8">
          {TRACK_ORDER.filter((t) => grouped[t].length > 0).map((track) => (
            <section key={track}>
              <div className={`flex items-center gap-2 mb-3 pb-2 border-b ${TRACK_SECTION[track]}`}>
                <span className={`text-xs font-bold px-2.5 py-1 rounded-md border ${TRACK_COLOR[track]}`}>
                  {TRACK_LABEL[track]}
                </span>
                <span className="text-xs text-slate-500 font-medium">{grouped[track].length}경주</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {grouped[track].map((race: any) => {
                  const status = getRaceStatus(race.post_time, race.completed);
                  return (
                    <div
                      key={race.id}
                      onClick={() => navigate(`/races/${date}/${race.id}`)}
                      className="group relative bg-white/5 border border-white/10 rounded-2xl p-4 shadow-lg cursor-pointer hover:bg-white/10 hover:border-indigo-500/40 active:scale-95 transition-all duration-200 overflow-hidden"
                    >
                      <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/5 to-purple-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
                      <div className="flex justify-between items-start mb-2">
                        <span className="font-semibold text-slate-100">
                          {race.race_name && !race.race_name.includes("경주")
                            ? `${race.race_name}`
                            : `제${race.race_number}경주`}
                        </span>
                        <div className="flex items-center gap-1.5">
                          {status && (
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${status.cls}`}>
                              {status.label}
                            </span>
                          )}
                          <span className="text-sm font-medium text-slate-400">
                            {race.post_time ? format(parseRaceTime(race.post_time)!, "HH:mm") : ""}
                          </span>
                        </div>
                      </div>
                      <div className="text-xs text-slate-500 font-medium flex gap-3">
                        <span>제{race.race_number}경주</span>
                        <span>📏 {race.distance_m}m</span>
                        <span>🐎 {race.field_size}두</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
