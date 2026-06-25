export function ProbabilityBar({ probability, color = "bg-blue-600" }: { probability: number, color?: string }) {
  const percent = Math.round(probability * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="w-full bg-gray-200 rounded-full h-2.5">
        <div className={`h-2.5 rounded-full ${color}`} style={{ width: `${percent}%` }}></div>
      </div>
      <span className="text-sm font-medium w-8">{percent}%</span>
    </div>
  );
}
