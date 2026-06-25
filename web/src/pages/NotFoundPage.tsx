import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="max-w-md mx-auto min-h-screen flex flex-col items-center justify-center p-4 bg-gray-50 text-center">
      <h1 className="text-4xl font-bold text-slate-900 mb-2">404</h1>
      <p className="text-gray-500 mb-6">Page not found</p>
      <Link to="/" className="text-blue-600 hover:underline">Go Home</Link>
    </div>
  );
}
