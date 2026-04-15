"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getProfiles, deleteProfile, ProfileResponse } from "@/lib/api";

const DECISION_LABELS: Record<string, string> = {
  release_readiness:     "Release readiness",
  incident_response:     "Incident response",
  sprint_planning:       "Sprint planning",
  team_health_review:    "Team health review",
  stakeholder_reporting: "Stakeholder reporting",
};

const CRITICALITY_LABEL: Record<string, string> = {
  mission_critical:   "Mission critical",
  business_important: "Business important",
  internal_tooling:   "Internal tooling",
};

const CRITICALITY_STYLE: Record<string, string> = {
  mission_critical:   "bg-rose-50 text-rose-700 border border-rose-200",
  business_important: "bg-amber-50 text-amber-700 border border-amber-200",
  internal_tooling:   "bg-slate-100 text-slate-600 border border-slate-200",
};

function daysAgo(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  if (days === 0) return "today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

const TrashIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
    <path d="M10 11v6M14 11v6" />
    <path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2" />
  </svg>
);

export default function Home() {
  const router = useRouter();

  // Modal state
  const [showModal, setShowModal]         = useState(false);
  const [profiles, setProfiles]           = useState<ProfileResponse[]>([]);
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [deleting, setDeleting]           = useState(false);
  const [search, setSearch]               = useState("");

  const openModal = () => {
    setShowModal(true);
    setLoadingProfiles(true);
    getProfiles()
      .then(setProfiles)
      .catch(() => setProfiles([]))
      .finally(() => setLoadingProfiles(false));
  };

  const closeModal = () => {
    setShowModal(false);
    setDeleteConfirm(null);
  };

  const handleDelete = async (id: string) => {
    setDeleting(true);
    try {
      await deleteProfile(id);
      setProfiles((prev) => prev.filter((p) => p.id !== id));
    } finally {
      setDeleting(false);
      setDeleteConfirm(null);
    }
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8 bg-slate-50">
      {/* Background grid */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#e2e8f0_1px,transparent_1px),linear-gradient(to_bottom,#e2e8f0_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_80%_60%_at_50%_50%,black,transparent)]" />

      <div className="relative max-w-lg text-center">
        {/* Logo mark */}
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-6" style={{ backgroundColor: "#1B6EF3" }}>
          <span className="text-white text-2xl font-black">M</span>
        </div>

        <h1 className="text-5xl font-black text-slate-900 mb-3 tracking-tight">
          MetricMind
        </h1>
        <p className="text-lg text-slate-500 mb-10 leading-relaxed">
          AI-powered DevOps decision intelligence.<br />
          Understand cross-metric trade-offs and receive<br />
          stakeholder-ready recommendations.
        </p>

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href="/onboarding"
            className="inline-flex items-center justify-center gap-2 text-white py-3 px-7 rounded-xl font-semibold text-sm"
            style={{ backgroundColor: "#1B6EF3" }}
          >
            New profile
          </Link>
          <Link
            href="/dashboard?demo=true"
            className="inline-flex items-center justify-center gap-2 bg-white text-slate-700 border border-slate-200 py-3 px-7 rounded-xl font-semibold hover:bg-slate-50 text-sm shadow-sm"
          >
            Try demo
          </Link>
          <button
            type="button"
            onClick={openModal}
            className="inline-flex items-center justify-center gap-2 bg-white text-slate-700 border border-slate-200 py-3 px-7 rounded-xl font-semibold hover:bg-slate-50 text-sm shadow-sm"
          >
            Saved profiles
          </button>
        </div>

        <p className="mt-8 text-xs text-slate-400">
          Powered by Claude · GitLab · Jira
        </p>

        <div className="mt-6">
          <Link
            href="/catalog"
            className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-violet-600 transition-colors font-medium"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h10" />
            </svg>
            Browse metric catalog
          </Link>
        </div>
      </div>

      {/* Saved profiles modal */}
      {showModal && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
          onClick={closeModal}
        >
          <div
            className="bg-white rounded-2xl shadow-xl w-full max-w-[960px] flex flex-col max-h-[80vh]"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <p className="text-sm font-bold text-slate-900">Saved profiles</p>
              <button
                type="button"
                aria-label="Close"
                onClick={closeModal}
                className="text-slate-400 hover:text-slate-600 transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>

            {/* Search */}
            <div className="px-6 py-3 border-b border-slate-100">
              <input
                type="text"
                placeholder="Search profiles..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent bg-white"
              />
            </div>

            {/* Column header row */}
            <div
              className="profile-grid-header px-6 py-2 border-b border-slate-100 bg-slate-50"
            >
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Team</span>
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Criticality</span>
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Decision</span>
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider text-right">Last analysis</span>
              <span />
              <span />
              <span />
            </div>

            {/* Modal body */}
            <div className="overflow-y-auto flex-1">
              {loadingProfiles ? (
                <div className="flex items-center justify-center py-16">
                  <div className="w-5 h-5 border-2 border-violet-600 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : (() => {
                const filtered = profiles.filter((p) =>
                  (p.team_name ?? "").toLowerCase().includes(search.toLowerCase())
                );
                if (filtered.length === 0) {
                  return (
                    <p className="text-center text-sm text-slate-400 py-16 px-6">
                      {profiles.length === 0
                        ? "No saved profiles yet. Create your first profile to get started."
                        : "No profiles match your search."}
                    </p>
                  );
                }
                return (
                  <ul>
                    {filtered.map((p) => (
                      <li
                        key={p.id}
                        className="profile-grid-row px-6 border-b border-slate-100 last:border-b-0 hover:bg-slate-50/60 transition-colors"
                      >
                        {/* Col 1: Team name */}
                        <span
                          className="text-sm font-bold text-slate-900 truncate"
                          title={p.team_name || "Unnamed profile"}
                        >
                          {p.team_name ? p.team_name : <em className="text-slate-400 font-normal">Unnamed profile</em>}
                        </span>

                        {/* Col 2: Criticality badge — fixed 120px */}
                        <span className={`profile-badge-crit inline-flex items-center justify-center rounded-md text-xs font-semibold ${CRITICALITY_STYLE[p.business_criticality] ?? "bg-slate-100 text-slate-600 border border-slate-200"}`}>
                          {CRITICALITY_LABEL[p.business_criticality] ?? p.business_criticality}
                        </span>

                        {/* Col 3: Decision badge — fixed 130px */}
                        <span
                          className="profile-badge-decision inline-flex items-center justify-center rounded-md text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200"
                        >
                          {DECISION_LABELS[p.decision_type] ?? p.decision_type}
                        </span>

                        {/* Col 4: Last analysis */}
                        <span className="text-xs text-slate-400 text-right whitespace-nowrap">
                          {p.last_analysis_at ? `Last analysis: ${daysAgo(p.last_analysis_at)}` : "No analysis yet"}
                        </span>

                        {/* Col 5: Dashboard button */}
                        <button
                          type="button"
                          onClick={() => { router.push(`/dashboard?profile_id=${p.id}`); closeModal(); }}
                          className="profile-btn-dash text-xs font-semibold bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-700 py-1.5 rounded-lg transition-colors"
                        >
                          Dashboard
                        </button>

                        {/* Col 6: Analyse button */}
                        <button
                          type="button"
                          onClick={() => { router.push(`/intelligence?profile_id=${p.id}`); closeModal(); }}
                          className="profile-btn-analyse text-xs font-semibold text-white py-1.5 rounded-lg transition-colors"
                          style={{ backgroundColor: "#1B6EF3" }}
                        >
                          Analyse
                        </button>

                        {/* Col 7: Trash */}
                        <button
                          type="button"
                          aria-label="Delete profile"
                          onClick={() => setDeleteConfirm(p.id)}
                          className="profile-btn-trash flex items-center justify-center text-slate-300 hover:text-rose-500 transition-colors"
                        >
                          <TrashIcon />
                        </button>
                      </li>
                    ))}
                  </ul>
                );
              })()}
            </div>
          </div>
        </div>
      )}

      {/* Delete confirmation modal */}
      {deleteConfirm && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-4"
          onClick={() => setDeleteConfirm(null)}
        >
          <div
            className="bg-white rounded-2xl p-6 max-w-sm w-full shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-sm font-semibold text-slate-900 mb-2">Delete this profile?</p>
            <p className="text-sm text-slate-500 mb-6">This cannot be undone.</p>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setDeleteConfirm(null)}
                disabled={deleting}
                className="flex-1 btn-secondary text-sm py-2"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleDelete(deleteConfirm)}
                disabled={deleting}
                className="flex-1 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-sm font-semibold py-2 disabled:opacity-40"
              >
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
