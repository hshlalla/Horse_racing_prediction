import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { register as registerApi } from "../api/auth";

const schema = z.object({
  email: z.string().email({ message: "유효한 이메일 주소를 입력하세요" }),
  password: z.string().min(8, { message: "비밀번호는 8자 이상이어야 합니다" }),
});
type FormValues = z.infer<typeof schema>;

export default function RegisterPage() {
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormValues>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: FormValues) => {
    try {
      await registerApi(data.email, data.password);
      navigate("/login");
    } catch (err: any) {
      setError(err.response?.data?.error?.message || "회원가입에 실패했습니다.");
    }
  };

  return (
    <div className="max-w-md mx-auto min-h-screen bg-slate-950 flex items-center justify-center p-6">
      <div className="w-full bg-slate-900 border border-white/10 rounded-2xl p-8 shadow-2xl">
        <h1 className="text-2xl font-black mb-2 text-center bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
          KRA Quant
        </h1>
        <p className="text-center text-slate-500 text-sm mb-8">회원가입</p>

        {error && (
          <div className="bg-rose-500/10 text-rose-400 border border-rose-500/30 p-3 rounded-xl mb-5 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5">이메일</label>
            <input
              type="email"
              {...register("email")}
              className={`w-full bg-white/5 border rounded-xl px-4 py-2.5 text-sm text-slate-200 outline-none focus:ring-2 transition-all placeholder:text-slate-600 [color-scheme:dark] ${
                errors.email ? "border-rose-500/50 focus:ring-rose-500/30" : "border-white/10 focus:ring-indigo-500/40 focus:border-indigo-500/50"
              }`}
              placeholder="user@example.com"
            />
            {errors.email && <p className="text-rose-400 text-xs mt-1">{errors.email.message}</p>}
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5">비밀번호</label>
            <input
              type="password"
              {...register("password")}
              className={`w-full bg-white/5 border rounded-xl px-4 py-2.5 text-sm text-slate-200 outline-none focus:ring-2 transition-all placeholder:text-slate-600 ${
                errors.password ? "border-rose-500/50 focus:ring-rose-500/30" : "border-white/10 focus:ring-indigo-500/40 focus:border-indigo-500/50"
              }`}
              placeholder="••••••••"
            />
            {errors.password && <p className="text-rose-400 text-xs mt-1">{errors.password.message}</p>}
          </div>
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full bg-indigo-500 hover:bg-indigo-600 active:bg-indigo-700 text-white font-bold py-3 rounded-xl transition-colors disabled:opacity-50 mt-2"
          >
            {isSubmitting ? "가입 중..." : "회원가입"}
          </button>
        </form>

        <p className="mt-5 text-center text-xs text-slate-500">
          이미 계정이 있으신가요?{" "}
          <Link to="/login" className="text-indigo-400 hover:text-indigo-300 font-semibold transition-colors">
            로그인
          </Link>
        </p>
      </div>
    </div>
  );
}
