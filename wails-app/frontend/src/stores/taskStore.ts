import { create } from 'zustand';
import { backend, mover } from '../../wailsjs/go/models';

export type TaskStatus = 'idle' | 'scanning' | 'searching' | 'moving' | 'error';

export interface ProgressEvent {
  type: 'info' | 'error' | 'clear' | 'success' | 'warning' | 'debug';
  message: string;
  timestamp: number;
}

export interface TaskState {
  // Directory
  inputDir: string;
  outputDir: string;
  setInputDir: (dir: string) => void;
  setOutputDir: (dir: string) => void;

  // Task status
  status: TaskStatus;
  setStatus: (status: TaskStatus) => void;

  // Scan results
  scanResults: backend.ScanResult[];
  setScanResults: (results: backend.ScanResult[]) => void;
  clearScanResults: () => void;

  // Search results
  searchResults: backend.SearchResult[];
  setSearchResults: (results: backend.SearchResult[]) => void;
  addSearchResult: (result: backend.SearchResult) => void;
  clearSearchResults: () => void;

  // Progress
  progress: number; // 0-100
  progressTotal: number;
  progressCurrent: number;
  setProgress: (current: number, total: number) => void;
  resetProgress: () => void;

  // Event log
  events: ProgressEvent[];
  pushEvent: (type: ProgressEvent['type'], message: string) => void;
  clearEvents: () => void;

  // Status bar message
  statusMessage: string;
  statusType: 'info' | 'error' | 'success' | 'warning';
  setStatusMessage: (msg: string, type?: TaskState['statusType']) => void;

  // Selected items
  selectedCodes: Set<string>;
  toggleSelected: (code: string) => void;
  selectAll: () => void;
  clearSelection: () => void;

  // Operation results
  lastBatchResult: mover.BatchResult | null;
  setLastBatchResult: (result: mover.BatchResult | null) => void;

  // UI flags
  showPreferences: boolean;
  showOperationHistory: boolean;
  showSearchResults: boolean;
  setShowPreferences: (v: boolean) => void;
  setShowOperationHistory: (v: boolean) => void;
  setShowSearchResults: (v: boolean) => void;

  // Debug mode
  debugMode: boolean;
  setDebugMode: (v: boolean) => void;

  // Conflict strategy
  conflictStrategy: 'skip' | 'overwrite' | 'rename';
  setConflictStrategy: (s: 'skip' | 'overwrite' | 'rename') => void;

  // Workers count
  scanWorkers: number;
  setScanWorkers: (n: number) => void;

  // Recursive scan
  recursive: boolean;
  setRecursive: (v: boolean) => void;
}

export const useTaskStore = create<TaskState>((set, get) => ({
  inputDir: '',
  outputDir: '',
  setInputDir: (dir) => set({ inputDir: dir }),
  setOutputDir: (dir) => set({ outputDir: dir }),

  status: 'idle',
  setStatus: (status) => set({ status }),

  scanResults: [],
  setScanResults: (results) => set({ scanResults: results }),
  clearScanResults: () => set({ scanResults: [] }),

  searchResults: [],
  setSearchResults: (results) => set({ searchResults: results }),
  addSearchResult: (result) =>
    set((state) => ({
      searchResults: [...state.searchResults, result],
    })),
  clearSearchResults: () => set({ searchResults: [] }),

  progress: 0,
  progressTotal: 0,
  progressCurrent: 0,
  setProgress: (current, total) =>
    set({
      progressCurrent: current,
      progressTotal: total,
      progress: total > 0 ? Math.round((current / total) * 100) : 0,
    }),
  resetProgress: () =>
    set({ progress: 0, progressCurrent: 0, progressTotal: 0 }),

  events: [],
  pushEvent: (type, message) =>
    set((state) => ({
      events: [
        ...state.events.slice(-199), // keep last 200 events
        { type, message, timestamp: Date.now() },
      ],
    })),
  clearEvents: () => set({ events: [] }),

  statusMessage: '就緒',
  statusType: 'info',
  setStatusMessage: (msg, type = 'info') =>
    set({ statusMessage: msg, statusType: type }),

  selectedCodes: new Set(),
  toggleSelected: (code) =>
    set((state) => {
      const next = new Set(state.selectedCodes);
      if (next.has(code)) {
        next.delete(code);
      } else {
        next.add(code);
      }
      return { selectedCodes: next };
    }),
  selectAll: () =>
    set((state) => ({
      selectedCodes: new Set(state.scanResults.map((r) => r.code)),
    })),
  clearSelection: () => set({ selectedCodes: new Set() }),

  lastBatchResult: null,
  setLastBatchResult: (result) => set({ lastBatchResult: result }),

  showPreferences: false,
  showOperationHistory: false,
  showSearchResults: false,
  setShowPreferences: (v) => set({ showPreferences: v }),
  setShowOperationHistory: (v) => set({ showOperationHistory: v }),
  setShowSearchResults: (v) => set({ showSearchResults: v }),

  debugMode: false,
  setDebugMode: (v) => set({ debugMode: v }),

  conflictStrategy: 'skip',
  setConflictStrategy: (s) => set({ conflictStrategy: s }),

  scanWorkers: 10,
  setScanWorkers: (n) => set({ scanWorkers: n }),

  recursive: true,
  setRecursive: (v) => set({ recursive: v }),
}));
