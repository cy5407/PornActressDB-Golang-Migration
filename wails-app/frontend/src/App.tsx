import { useState } from 'react';
import logo from './assets/images/logo-universal.png';
import './App.css';
import { ScanDirectory } from '../wailsjs/go/backend/App';
import { backend } from '../wailsjs/go/models';

type ScanResult = backend.ScanResult;

function App() {
    const [dirPath, setDirPath] = useState('');
    const [results, setResults] = useState<ScanResult[]>([]);
    const [scanning, setScanning] = useState(false);
    const [error, setError] = useState('');

    function handleScan() {
        if (!dirPath.trim()) {
            setError('請輸入目錄路徑');
            return;
        }
        setScanning(true);
        setError('');
        setResults([]);
        ScanDirectory(dirPath)
            .then((res) => {
                setResults(res ?? []);
            })
            .catch((err) => {
                setError(String(err));
            })
            .finally(() => {
                setScanning(false);
            });
    }

    return (
        <div id="App">
            <img src={logo} id="logo" alt="logo" />
            <h1>女優分類系統 — Wails PoC</h1>
            <div className="input-box">
                <input
                    className="input"
                    type="text"
                    value={dirPath}
                    onChange={(e) => setDirPath(e.target.value)}
                    placeholder="輸入目錄路徑，例如 /videos"
                    autoComplete="off"
                />
                <button className="btn" onClick={handleScan} disabled={scanning}>
                    {scanning ? '掃描中…' : '掃描目錄'}
                </button>
            </div>
            {error && <p style={{ color: 'red' }}>{error}</p>}
            <div id="result" className="result">
                {results.length > 0 ? (
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr>
                                <th style={{ textAlign: 'left', padding: '4px 8px' }}>番號</th>
                                <th style={{ textAlign: 'left', padding: '4px 8px' }}>檔案路徑</th>
                            </tr>
                        </thead>
                        <tbody>
                            {results.map((r, i) => (
                                <tr key={i} style={{ borderTop: '1px solid #333' }}>
                                    <td style={{ padding: '4px 8px', fontWeight: 'bold' }}>{r.code}</td>
                                    <td style={{ padding: '4px 8px', wordBreak: 'break-all' }}>{r.path}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : (
                    !scanning && <p>尚無結果</p>
                )}
            </div>
        </div>
    );
}

export default App;

