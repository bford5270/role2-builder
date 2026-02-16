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
        case_book: 'docx'
      };
      const labels: Record<string, string> = {
        msel: 'MSEL',
        warno: 'WARNO',
        annex_q: 'Annex_Q',
        medroe: 'MEDROE',
        case_book: 'Case_Book'
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
    <div className="min-h-screen bg-stone-900 text-amber-100 p-6">
      <div className="max-w-6xl mx-auto">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-amber-400">Historic Exercises</h1>
            <p className="text-stone-400">View and download past exercise packages</p>
          </div>
          <a href="/" className="text-amber-400 hover:text-amber-300 text-sm">← New Exercise</a>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-12">
            <svg className="animate-spin h-8 w-8 text-amber-400" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="ml-3">Loading exercises...</span>
          </div>
        )}

        {error && (
          <div className="bg-red-900/50 border border-red-700 rounded-lg p-4 mb-6">
            <p className="text-red-300">{error}</p>
          </div>
        )}

        {!loading && exercises.length === 0 && (
          <div className="bg-stone-800 border border-stone-700 rounded-lg p-8 text-center">
            <p className="text-stone-400 mb-4">No exercises found</p>
            <a href="/" className="text-amber-400 hover:text-amber-300 underline">Create your first exercise →</a>
          </div>
        )}

        <div className="space-y-4">
          {exercises.map((exercise) => (
            <div key={exercise.id} className="bg-stone-800 border border-stone-700 rounded-lg p-4">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h2 className="text-lg font-semibold text-amber-400">{exercise.name}</h2>
                  <p className="text-xs text-stone-400">{formatDate(exercise.created_at)}</p>
                </div>
                <button
                  onClick={() => downloadPackage(exercise.id, exercise.name)}
                  disabled={downloading === exercise.id}
                  className={`px-4 py-2 rounded font-medium text-sm transition-all ${
                    downloading === exercise.id
                      ? 'bg-stone-700 text-stone-500 cursor-wait'
                      : 'bg-amber-600 hover:bg-amber-500 text-stone-900'
                  }`}
                >
                  {downloading === exercise.id ? 'Downloading...' : 'Download ZIP'}
                </button>
              </div>

              <div className="grid grid-cols-3 gap-4 mb-4 text-sm">
                <div>
                  <span className="text-stone-400">Duration:</span>
                  <span className="ml-2">{exercise.duration || 'N/A'} days</span>
                </div>
                <div>
                  <span className="text-stone-400">Environment:</span>
                  <span className="ml-2">{exercise.environment || 'N/A'}</span>
                </div>
                <div>
                  <span className="text-stone-400">Cases:</span>
                  <span className="ml-2">{exercise.total_cases}</span>
                </div>
              </div>

              <div className="border-t border-stone-700 pt-3">
                <p className="text-xs text-stone-400 mb-2">Individual Documents</p>
                <div className="flex flex-wrap gap-2">
                  {[
                    { key: 'msel', label: 'MSEL', icon: '📊' },
                    { key: 'warno', label: 'WARNO', icon: '📄' },
                    { key: 'annex_q', label: 'Annex Q', icon: '🏥' },
                    { key: 'medroe', label: 'MEDROE', icon: '⚖️' },
                    { key: 'case_book', label: 'Case Book', icon: '📚' }
                  ].map(doc => (
                    <button
                      key={doc.key}
                      onClick={() => downloadDocument(exercise.id, exercise.name, doc.key)}
                      className="flex items-center gap-1 px-3 py-1 bg-stone-700 hover:bg-stone-600 rounded text-xs transition-colors"
                    >
                      <span>{doc.icon}</span>
                      <span>{doc.label}</span>
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
