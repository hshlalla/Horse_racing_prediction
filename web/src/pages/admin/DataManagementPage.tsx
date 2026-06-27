import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchDataStatus,
  retryDate,
} from "../../api/admin";
import type { CrawlFailureInfo, CrawlStateInfo } from "../../api/admin";

function CrawlStateRow({ state }: { state: CrawlStateInfo }) {
  const statusColor =
    state.last_status === "ok"
      ? "text-emerald-400"
      : state.last_status === "partial"
      ? "text-yellow-400"
      : "text-slate-500";

  return (
    <div className="flex justify-between items-center py-3 border-b border-white/5 last:border-0">
      <span className="font-medium text-slate-200">{state.track}</span>
      <div className="text-right">
        <div className={`text-sm font-mono ${statusColor}`}>
          {state.last_status || "never run"}
        </div>
        <div className="text-xs text-slate-500">
          {state.last_crawled_date
            ? `최근: ${state.last_crawled_date}`
            : "크롤 이력 없음"}
        </div>
      </div>
    </div>
  );
}

function FailureRow({
  failure,
  onRetry,
  isRetrying,
}: {
  failure: CrawlFailureInfo;
  onRetry: (track: string, date: string) => void;
  isRetrying: boolean;
}) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-3 flex justify-between items-start gap-3">
      <div className="flex-1 min-w-0">
        <div className="font-medium text-slate-200 text-sm">
          {failure.track} — {failure.failed_date}
        </div>
        <div className="text-xs text-slate-500 truncate mt-0.5">
          {failure.error_message || "알 수 없는 오류"}
        </div>
        <div className="text-xs text-slate-600 mt-1">
          재시도 {failure.retry_count}회
        </div>
      </div>
      <button
        onClick={() => onRetry(failure.track, failure.failed_date)}
        disabled={isRetrying}
        className="text-xs bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 rounded-lg px-3 py-1.5 hover:bg-indigo-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
      >
        {isRetrying ? "재시도 중..." : "재시도"}
      </button>
    </div>
  );
}

export default function DataManagementPage() {
  const queryClient = useQueryClient();
  const [retryingId, setRetryingId] = useState<number | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "data", "status"],
    queryFn: fetchDataStatus,
    refetchInterval: 30_000,
  });

  const retryMutation = useMutation({
    mutationFn: ({ track, date }: { track: string; date: string }) =>
      retryDate(track, date),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "data", "status"] });
      setRetryingId(null);
    },
    onError: () => setRetryingId(null),
  });

  const handleRetry = (failureId: number, track: string, date: string) => {
    setRetryingId(failureId);
    retryMutation.mutate({ track, date });
  };

  if (isLoading)
    return (
      <div className="text-slate-500 text-center mt-10">Loading...</div>
    );
  if (error)
    return (
      <div className="max-w-2xl mx-auto p-4">
        <div className="text-red-400 bg-red-500/10 border border-red-500/30 rounded-xl p-4">
          Failed to load data status.
        </div>
      </div>
    );

  return (
    <div className="max-w-2xl mx-auto min-h-screen bg-slate-950 text-slate-200 p-4">
      <h1 className="text-2xl font-bold text-slate-100 mb-6">데이터 관리</h1>

      {/* DB Summary */}
      <section className="mb-6">
        <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-3">
          DB 현황
        </h2>
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: "레이스", value: data?.db_summary.total_races },
            { label: "말", value: data?.db_summary.total_horses },
            { label: "기수", value: data?.db_summary.total_jockeys },
            {
              label: "최신 데이터",
              value: data?.db_summary.latest_race_date ?? "없음",
            },
          ].map(({ label, value }) => (
            <div
              key={label}
              className="bg-white/5 border border-white/10 rounded-xl p-3"
            >
              <div className="text-slate-500 text-xs mb-1">{label}</div>
              <div className="font-mono text-slate-200 font-bold">
                {value?.toLocaleString() ?? "—"}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Crawl Status */}
      <section className="mb-6">
        <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-3">
          크롤 상태
        </h2>
        <div className="bg-white/5 border border-white/10 rounded-xl px-4">
          {data?.crawl_states.map((s) => (
            <CrawlStateRow key={s.track} state={s} />
          ))}
        </div>
      </section>

      {/* Failures */}
      <section>
        <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-3">
          실패 목록{" "}
          {data?.failures.length ? (
            <span className="text-red-400">({data.failures.length})</span>
          ) : (
            <span className="text-emerald-400">(없음)</span>
          )}
        </h2>
        {data?.failures.length === 0 ? (
          <div className="text-slate-500 text-sm text-center py-6">
            실패한 크롤이 없습니다.
          </div>
        ) : (
          <div className="space-y-2">
            {data?.failures.map((f) => (
              <FailureRow
                key={f.id}
                failure={f}
                onRetry={(track, date) => handleRetry(f.id, track, date)}
                isRetrying={retryingId === f.id}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
