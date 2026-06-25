import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { register as registerApi } from "../api/auth";
import { useTranslation } from "../hooks/useTranslation";

const registerSchema = z.object({
  email: z.string().email({ message: "Invalid email address" }),
  password: z.string().min(8, { message: "Password must be at least 8 characters" }),
});

type RegisterFormValues = z.infer<typeof registerSchema>;

export default function RegisterPage() {
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const { t } = useTranslation();

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema)
  });

  const onSubmit = async (data: RegisterFormValues) => {
    try {
      await registerApi(data.email, data.password);
      navigate("/login");
    } catch (err: any) {
      setError(err.response?.data?.error?.message || "Registration failed");
    }
  };

  return (
    <div className="max-w-md mx-auto min-h-screen flex items-center justify-center p-4 bg-gray-50">
      <div className="bg-white p-8 rounded-xl shadow-lg w-full">
        <h1 className="text-2xl font-bold mb-6 text-center text-slate-900">{t("app.register")}</h1>
        {error && <div className="bg-red-50 text-red-600 p-3 rounded mb-4 text-sm">{error}</div>}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Email</label>
            <input 
              type="email" 
              {...register("email")}
              className={`w-full border rounded p-2 outline-none focus:ring-1 ${errors.email ? 'border-red-500 focus:ring-red-500' : 'focus:border-blue-500 focus:ring-blue-500'}`}
            />
            {errors.email && <p className="text-red-500 text-xs mt-1">{errors.email.message}</p>}
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Password</label>
            <input 
              type="password" 
              {...register("password")}
              className={`w-full border rounded p-2 outline-none focus:ring-1 ${errors.password ? 'border-red-500 focus:ring-red-500' : 'focus:border-blue-500 focus:ring-blue-500'}`}
            />
            {errors.password && <p className="text-red-500 text-xs mt-1">{errors.password.message}</p>}
          </div>
          <button 
            type="submit" 
            disabled={isSubmitting}
            className="w-full bg-slate-900 text-white font-bold py-2 rounded hover:bg-slate-800 transition-colors disabled:opacity-50"
          >
            {isSubmitting ? "Registering..." : t("app.register")}
          </button>
        </form>
        <div className="mt-4 text-center text-sm">
          Already have an account? <Link to="/login" className="text-blue-600 hover:underline">{t("app.login")}</Link>
        </div>
      </div>
    </div>
  );
}
