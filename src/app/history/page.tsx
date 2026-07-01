'use client';

import React, { useState, useEffect } from 'react';

interface ExerciseSummary {
  id: number;
  name: string;
  created_at: string | null;
  duration: number | null;
  environment: string | null;
  total_cases: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'https://role2-builder-production.up.railway.app';

export default function HistoricExercisesPage() {
  const [exercises, setExercises] = useState<ExerciseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<number | null>(null);

  useEffect(() => {
    fetchExercises();
  }, []);

  const fetchExercises = async () => {
    try {
      const response = await fetch(`${API_BASE}/exercises`);
      if (!response.ok) throw new Error('Failed to fetch exercises');
      const data = await response.json();
      setExercises(data.exercises);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load exercises');
    } finally {
      setLoading(false);
    }
  };

  const downloadPackage = async (exerciseId: number, exerciseName: string) => {
    setDownloading(exerciseId);
    try {
      const response = await fetch(`${API_BASE}/exercises/${exerciseId}/download`);
      if (!response.ok) throw new Error('Download failed');
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${exerciseName}_Package.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      alert('Failed to download package');
    } finally {
      setDownloading(null);
    }
  };

  const downloadDocument = async (exerciseId: number, exerciseName: string, docType: string) => {
    try {
      const response = await fetch(`${API_BASE}/exercises/${exerciseId}/document/${docType}`);
      if (!response.ok) throw new Error('Download failed');
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      
      const extensions: Record<string, string> = {
        msel: 'xlsx',
        warno: 'docx',
        annex_q: 'docx',
        medroe: 'docx',
        case_book: 'docx',
        road_to_war: 'docx'
      };
      const labels: Record<string, string> = {
        msel: 'MSEL',
        warno: 'WARNO',
        annex_q: 'Annex_Q',
        medroe: 'MEDROE',
        case_book: 'Case_Book',
        road_to_war: 'Road_to_War_Prompt'
      };
      
      a.download = `${exerciseName}_${labels[docType]}.${extensions[docType]}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      alert('Failed to download document');
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="min-h-screen bg-surface-0 text-ink-1 p-6">
      <div className="max-w-6xl mx-auto">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold font-display tracking-display text-ink-1">Historic exercises</h1>
            <p className="text-ink-3 text-sm">View and download past exercise packages</p>
          </div>
          <a href="/" className="text-accent hover:text-accent-hover text-sm">← New exercise</a>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-12 text-ink-2">
            <svg className="animate-spin h-6 w-6 text-accent" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="ml-3">Loading exercises...</span>
          </div>
        )}

        {error && (
          <div className="bg-surface-2 border-l-4 border-signal-red rounded p-4 mb-6">
            <p className="text-signal-red text-sm">{error}</p>
          </div>
        )}

        {!loading && exercises.length === 0 && (
          <div className="bg-surface-1 border border-border-1 rounded p-8 text-center">
            <p className="text-ink-3 mb-4">No exercises found.</p>
            <a href="/" className="text-accent hover:text-accent-hover underline">Create your first exercise →</a>
          </div>
        )}

        <div className="space-y-4">
          {exercises.map((exercise) => (
            <div key={exercise.id} className="bg-surface-1 border border-border-1 rounded p-4">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h2 className="text-lg font-medium font-display text-ink-1">{exercise.name}</h2>
                  <p className="text-xs font-mono text-ink-3 mt-0.5">{formatDate(exercise.created_at)}</p>
                </div>
                <button
                  onClick={() => downloadPackage(exercise.id, exercise.name)}
                  disabled={downloading === exercise.id}
                  className={`px-4 py-2 rounded font-semibold text-xs uppercase tracking-caps transition-colors ${
                    downloading === exercise.id
                      ? 'bg-surface-3 text-ink-3 cursor-wait'
                      : 'bg-accent hover:bg-accent-hover text-accent-on'
                  }`}
                >
                  {downloading === exercise.id ? 'Downloading...' : 'Download zip'}
                </button>
              </div>

              <div className="grid grid-cols-3 gap-4 mb-4 text-sm">
                <div>
                  <span className="text-xs uppercase tracking-caps text-ink-3">Duration</span>
                  <span className="ml-2 font-mono text-ink-1">{exercise.duration || 'N/A'} days</span>
                </div>
                <div>
                  <span className="text-xs uppercase tracking-caps text-ink-3">Environment</span>
                  <span className="ml-2 text-ink-1">{exercise.environment || 'N/A'}</span>
                </div>
                <div>
                  <span className="text-xs uppercase tracking-caps text-ink-3">Cases</span>
                  <span className="ml-2 font-mono text-ink-1">{exercise.total_cases}</span>
                </div>
              </div>

              <div className="border-t border-border-1 pt-3">
                <p className="text-xs font-semibold uppercase tracking-caps text-ink-3 mb-2">Individual documents</p>
                <div className="flex flex-wrap gap-2">
                  {[
                    { key: 'msel', label: 'MSEL' },
                    { key: 'warno', label: 'WARNO' },
                    { key: 'annex_q', label: 'Annex Q' },
                    { key: 'medroe', label: 'MEDROE' },
                    { key: 'case_book', label: 'Case book' },
                    { key: 'road_to_war', label: 'Road to War' }
                  ].map(doc => (
                    <button
                      key={doc.key}
                      onClick={() => downloadDocument(exercise.id, exercise.name, doc.key)}
                      className="px-3 py-1 bg-surface-2 hover:bg-surface-3 border border-border-1 text-ink-2 rounded text-xs transition-colors"
                    >
                      {doc.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
