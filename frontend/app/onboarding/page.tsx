import Link from "next/link";
import ProfileWizard from "@/components/ProfileWizard";

export default function OnboardingPage() {
  return (
    <main className="min-h-screen bg-slate-50 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-6 group">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            Back to home
          </Link>
          <div className="flex items-center gap-3 mb-1">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ backgroundColor: "#1B6EF3" }}>
              <span className="text-white text-base font-black">M</span>
            </div>
            <span className="text-sm font-semibold text-slate-400 tracking-wide uppercase">MetricMind</span>
          </div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">Set up your profile</h1>
          <p className="text-slate-500 mt-1 text-sm">Configure your team context to get tailored metric analysis.</p>
        </div>

        <ProfileWizard />
      </div>
    </main>
  );
}
