import { useNavigate } from "react-router-dom";

export default function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <div className="max-w-md mx-auto min-h-screen bg-slate-950 flex flex-col items-center justify-center p-8 text-center">
      <span className="text-6xl mb-6">🏇</span>
      <h1 className="text-5xl font-black text-slate-700 mb-2">404</h1>
      <p className="text-slate-400 mb-8">페이지를 찾을 수 없습니다.</p>
      <button
        onClick={() => navigate("/")}
        className="bg-indigo-500 hover:bg-indigo-600 text-white font-bold px-6 py-2.5 rounded-xl transition-colors"
      >
        홈으로
      </button>
    </div>
  );
}
