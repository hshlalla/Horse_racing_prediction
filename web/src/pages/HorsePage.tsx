import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

export default function HorsePage() {
  const { horseId } = useParams();
  const navigate = useNavigate();

  // In a full implementation, we would fetch horse details from /horses/{horseId}
  // For now, this is a placeholder page

  return (
    <div className="max-w-md mx-auto min-h-screen bg-gray-50">
      <header className="bg-slate-900 text-white p-4 sticky top-0 z-10 shadow-md">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)}><ArrowLeft size={20}/></button>
          <h1 className="text-xl font-bold">Horse {horseId}</h1>
        </div>
      </header>
      
      <div className="p-4 space-y-4">
        <div className="bg-white p-6 rounded-xl shadow-sm border text-center">
          <div className="w-20 h-20 bg-gray-200 rounded-full mx-auto mb-4 flex items-center justify-center text-gray-400">
            Image
          </div>
          <h2 className="text-2xl font-bold mb-1">Mock Horse Name</h2>
          <p className="text-gray-500 text-sm">Age: 4 • Sex: M</p>
        </div>
        
        <div className="bg-white p-4 rounded-xl shadow-sm border">
          <h3 className="font-bold text-lg mb-2">Recent Form</h3>
          <div className="text-gray-500 text-sm text-center py-4">
            Recent race history would appear here.
          </div>
        </div>
      </div>
    </div>
  );
}
