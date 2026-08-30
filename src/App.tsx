import React, { useRef, useEffect, useState, useCallback } from 'react';
import Webcam from 'react-webcam';
import { FilesetResolver, FaceLandmarker } from '@mediapipe/tasks-vision';
import {
  Camera, CameraOff, Activity, AlertCircle, Settings,
  Monitor, Volume2, VolumeX, Clock, Zap, X,
  CheckCircle2, TrendingDown, RefreshCcw
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Area, AreaChart
} from 'recharts';

const ALPHA = 0.7;
const THRESHOLD = 15.0;
const HOLD_MS = 800;
const MAX_CHART_POINTS = 80;

function rotationMatrixToEuler(matrix: number[]) {
  const m00 = matrix[0], m10 = matrix[4];
  const m12 = matrix[6], m11 = matrix[5];
  const m21 = matrix[9], m22 = matrix[10];

  const sy = Math.sqrt(m00 * m00 + m10 * m10);
  let pitch = sy > 1e-6
    ? Math.atan2(m21, m22) * (180 / Math.PI)
    : Math.atan2(-m12, m11) * (180 / Math.PI);

  return -pitch; // Inverted: forward bend = positive
}

// Custom tooltip for chart
const CustomTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const v = payload[0].value;
    return (
      <div className="bg-slate-800 border border-slate-600 px-3 py-2 rounded-lg text-sm shadow-xl">
        <p className={v >= THRESHOLD ? 'text-red-400 font-semibold' : 'text-emerald-400 font-semibold'}>
          {v.toFixed(1)}°
        </p>
      </div>
    );
  }
  return null;
};

export default function App() {
  const webcamRef = useRef<Webcam>(null);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [isLoaded, setIsLoaded] = useState(false);
  const [faceDetected, setFaceDetected] = useState(false);

  const [pitch, setPitch] = useState(0);
  const [baseline, setBaseline] = useState<number | null>(null);
  const [drop, setDrop] = useState(0);
  const [isSlouching, setIsSlouching] = useState(false);

  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [showCamera, setShowCamera] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [threshold, setThreshold] = useState(THRESHOLD);
  const [holdMs, setHoldMs] = useState(HOLD_MS);

  const [slouchCount, setSlouchCount] = useState(0);
  const [goodSeconds, setGoodSeconds] = useState(0);
  const [sessionStartTime, setSessionStartTime] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [chartData, setChartData] = useState<{ drop: number }[]>([]);

  const landmarkerRef = useRef<FaceLandmarker | null>(null);
  const requestRef = useRef<number>();
  const smoothedPitchRef = useRef<number>(0);
  const lastVideoTimeRef = useRef<number>(-1);
  const slouchStartRef = useRef<number | null>(null);
  const lastSlouchState = useRef<boolean>(false);
  const lastAlertTime = useRef<number>(0);

  const playAlert = useCallback(() => {
    if (!voiceEnabled) return;
    const now = Date.now();
    if (now - lastAlertTime.current < 5000) return; // 5s cooldown
    lastAlertTime.current = now;
    window.speechSynthesis.cancel();
    const msg = new SpeechSynthesisUtterance('Sit up straight!');
    msg.rate = 1.1;
    msg.pitch = 1;
    window.speechSynthesis.speak(msg);
  }, [voiceEnabled]);

  // Init MediaPipe
  useEffect(() => {
    const init = async () => {
      const fs = await FilesetResolver.forVisionTasks(
        'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.3/wasm'
      );
      const fl = await FaceLandmarker.createFromOptions(fs, {
        baseOptions: { modelAssetPath: '/face_landmarker.task', delegate: 'GPU' },
        outputFaceBlendshapes: false,
        outputFacialTransformationMatrixes: true,
        runningMode: 'VIDEO',
        numFaces: 1,
      });
      landmarkerRef.current = fl;
      setIsLoaded(true);
    };
    init();
  }, []);

  // Session timer
  useEffect(() => {
    if (!isMonitoring || !sessionStartTime) return;
    const interval = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - sessionStartTime) / 1000));
      if (!isSlouching && faceDetected && baseline !== null) {
        setGoodSeconds(g => g + 1);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [isMonitoring, sessionStartTime, isSlouching, faceDetected, baseline]);

  const processVideo = useCallback(() => {
    if (!isMonitoring || !webcamRef.current?.video || !landmarkerRef.current) return;
    const video = webcamRef.current.video;
    if (video.readyState !== 4) {
      requestRef.current = requestAnimationFrame(processVideo);
      return;
    }

    const nowMs = performance.now();
    if (video.currentTime !== lastVideoTimeRef.current) {
      lastVideoTimeRef.current = video.currentTime;
      const result = landmarkerRef.current.detectForVideo(video, nowMs);

      if (result.facialTransformationMatrixes?.length) {
        setFaceDetected(true);
        const rawPitch = rotationMatrixToEuler(result.facialTransformationMatrixes[0].data);

        if (smoothedPitchRef.current === 0) smoothedPitchRef.current = rawPitch;
        else smoothedPitchRef.current += ALPHA * (rawPitch - smoothedPitchRef.current);

        const finalPitch = smoothedPitchRef.current;
        setPitch(finalPitch);

        setBaseline(prev => {
          if (prev !== null) {
            const currentDrop = finalPitch - prev;
            setDrop(currentDrop);
            setChartData(old => {
              const next = [...old, { drop: parseFloat(currentDrop.toFixed(2)) }];
              return next.length > MAX_CHART_POINTS ? next.slice(-MAX_CHART_POINTS) : next;
            });

            if (currentDrop >= threshold) {
              if (!slouchStartRef.current) slouchStartRef.current = Date.now();
              else if (Date.now() - slouchStartRef.current > holdMs) {
                if (!lastSlouchState.current) {
                  setIsSlouching(true);
                  setSlouchCount(c => c + 1);
                  playAlert();
                }
                lastSlouchState.current = true;
              }
            } else {
              slouchStartRef.current = null;
              if (lastSlouchState.current) setIsSlouching(false);
              lastSlouchState.current = false;
            }
          }
          return prev;
        });
      } else {
        setFaceDetected(false);
      }
    }
    requestRef.current = requestAnimationFrame(processVideo);
  }, [isMonitoring, threshold, holdMs, playAlert]);

  useEffect(() => {
    if (isMonitoring) {
      if (!sessionStartTime) setSessionStartTime(Date.now());
      requestRef.current = requestAnimationFrame(processVideo);
    }
    return () => { if (requestRef.current) cancelAnimationFrame(requestRef.current); };
  }, [isMonitoring, processVideo, sessionStartTime]);

  const calibrate = () => {
    setBaseline(pitch);
    setDrop(0);
    setIsSlouching(false);
    lastSlouchState.current = false;
    slouchStartRef.current = null;
    setChartData([]);
    setSlouchCount(0);
    setGoodSeconds(0);
    setSessionStartTime(Date.now());
    setElapsedSeconds(0);
  };

  const goodPercent = elapsedSeconds > 0 ? Math.round((goodSeconds / elapsedSeconds) * 100) : 100;
  const dropPercent = Math.min(100, Math.max(0, (drop / threshold) * 100));

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60).toString().padStart(2, '0');
    const s = (secs % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  const statusText = () => {
    if (!isMonitoring) return { text: 'Paused', color: 'text-slate-400', icon: null };
    if (!faceDetected) return { text: 'No Face Detected', color: 'text-amber-400', icon: '👤' };
    if (baseline === null) return { text: 'Sit upright, then Calibrate', color: 'text-blue-400', icon: '📐' };
    if (isSlouching) return { text: 'Slouching! Sit up straight.', color: 'text-red-400', icon: '⚠️' };
    return { text: 'Great posture! Keep it up.', color: 'text-emerald-400', icon: '✓' };
  };

  const status = statusText();

  return (
    <div className="min-h-screen bg-[#0b0f1a] text-white font-sans flex flex-col">

      {/* Hidden webcam */}
      <Webcam
        ref={webcamRef} audio={false}
        videoConstraints={{ facingMode: 'user', width: 640, height: 480 }}
        className={showCamera
          ? 'fixed bottom-6 right-6 w-44 rounded-2xl border-2 border-slate-600 shadow-2xl z-50 opacity-80 hover:opacity-100 transition'
          : 'hidden'}
      />

      {/* Settings panel */}
      {showSettings && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center" onClick={() => setShowSettings(false)}>
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-8 w-full max-w-sm shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-lg font-semibold">Settings</h2>
              <button onClick={() => setShowSettings(false)} className="text-slate-400 hover:text-white"><X className="w-5 h-5"/></button>
            </div>

            <label className="block mb-6">
              <div className="flex justify-between text-sm text-slate-400 mb-2">
                <span>Slouch Threshold</span>
                <span className="font-mono text-white">{threshold}°</span>
              </div>
              <input type="range" min={5} max={30} value={threshold}
                onChange={e => setThreshold(Number(e.target.value))}
                className="w-full accent-blue-500"/>
              <p className="text-xs text-slate-500 mt-1">How far your head must drop before it counts</p>
            </label>

            <label className="block mb-6">
              <div className="flex justify-between text-sm text-slate-400 mb-2">
                <span>Alert Delay</span>
                <span className="font-mono text-white">{holdMs}ms</span>
              </div>
              <input type="range" min={200} max={3000} step={100} value={holdMs}
                onChange={e => setHoldMs(Number(e.target.value))}
                className="w-full accent-blue-500"/>
              <p className="text-xs text-slate-500 mt-1">How long you must slouch before an alert fires</p>
            </label>

            <div className="flex items-center justify-between py-3 border-t border-slate-700">
              <div>
                <p className="text-sm font-medium">Voice Alerts</p>
                <p className="text-xs text-slate-500">Speak "Sit up straight!" when detected</p>
              </div>
              <button onClick={() => setVoiceEnabled(!voiceEnabled)}
                className={`w-12 h-6 rounded-full transition-colors relative ${voiceEnabled ? 'bg-blue-600' : 'bg-slate-600'}`}>
                <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 transition-all ${voiceEnabled ? 'right-0.5' : 'left-0.5'}`}/>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Top Nav */}
      <nav className="px-8 py-5 flex items-center justify-between border-b border-slate-800/60 bg-[#0b0f1a]/80 backdrop-blur sticky top-0 z-40">
        <div className="flex items-center gap-3">
          <div className="bg-blue-600 p-2 rounded-xl">
            <Activity className="w-5 h-5 text-white"/>
          </div>
          <div>
            <h1 className="text-lg font-bold leading-none">PostureFix</h1>
            <p className="text-xs text-slate-500">Web Edition</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Status dot */}
          <div className={`w-2 h-2 rounded-full ${!isMonitoring ? 'bg-slate-600' : isSlouching ? 'bg-red-500 animate-pulse' : faceDetected && baseline !== null ? 'bg-emerald-500' : 'bg-amber-500'}`}/>
          
          <button onClick={() => setVoiceEnabled(!voiceEnabled)}
            className={`p-2 rounded-xl transition ${voiceEnabled ? 'text-blue-400 bg-blue-500/10' : 'text-slate-500 hover:text-slate-300'}`}>
            {voiceEnabled ? <Volume2 className="w-4 h-4"/> : <VolumeX className="w-4 h-4"/>}
          </button>
          <button onClick={() => setShowCamera(!showCamera)}
            className={`p-2 rounded-xl transition ${showCamera ? 'text-blue-400 bg-blue-500/10' : 'text-slate-500 hover:text-slate-300'}`}>
            {showCamera ? <Camera className="w-4 h-4"/> : <CameraOff className="w-4 h-4"/>}
          </button>
          <button onClick={() => setShowSettings(true)}
            className="p-2 rounded-xl text-slate-500 hover:text-slate-300 transition">
            <Settings className="w-4 h-4"/>
          </button>
        </div>
      </nav>

      {/* Main */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* LEFT */}
        <div className="space-y-5">

          {/* Big Status */}
          <div className={`rounded-2xl p-6 border transition-all duration-500 ${
            isSlouching
              ? 'bg-red-500/10 border-red-500/40 shadow-lg shadow-red-500/10'
              : baseline && faceDetected && isMonitoring
                ? 'bg-emerald-500/10 border-emerald-500/30'
                : 'bg-slate-800/60 border-slate-700/60'
          }`}>
            <div className="flex items-start justify-between mb-5">
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-widest font-medium mb-1">Status</p>
                <p className={`text-xl font-bold ${status.color}`}>
                  {status.icon} {status.text}
                </p>
              </div>
              {isSlouching && <AlertCircle className="w-8 h-8 text-red-400 animate-pulse flex-shrink-0"/>}
              {!isSlouching && baseline && isMonitoring && faceDetected &&
                <CheckCircle2 className="w-8 h-8 text-emerald-400 flex-shrink-0"/>}
            </div>

            {/* Drop bar */}
            <div className="mb-3">
              <div className="flex justify-between text-xs text-slate-500 mb-1.5">
                <span>Head Drop</span>
                <span className="font-mono">{drop.toFixed(1)}° / {threshold}°</span>
              </div>
              <div className="h-3 bg-slate-900 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-100 ${
                    dropPercent > 100 ? 'bg-red-500' : dropPercent > 70 ? 'bg-amber-500' : 'bg-emerald-500'
                  }`}
                  style={{ width: `${dropPercent}%` }}
                />
              </div>
            </div>

            <p className="text-xs text-slate-600 font-mono">Pitch: {pitch.toFixed(1)}°</p>
          </div>

          {/* Controls */}
          <div className="space-y-3">
            <button
              disabled={!isLoaded}
              onClick={() => setIsMonitoring(!isMonitoring)}
              className={`w-full py-3.5 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all duration-200 disabled:opacity-40 ${
                isMonitoring
                  ? 'bg-slate-700 hover:bg-slate-600 text-white'
                  : 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-500/20'
              }`}
            >
              {isLoaded ? (isMonitoring ? <Monitor className="w-4 h-4"/> : <Camera className="w-4 h-4"/>) : (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"/>
              )}
              {!isLoaded ? 'Loading model...' : isMonitoring ? 'Stop Monitoring' : 'Start Camera'}
            </button>

            <button
              disabled={!isMonitoring || !faceDetected}
              onClick={calibrate}
              className="w-full py-3.5 rounded-xl font-semibold bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 flex items-center justify-center gap-2 transition disabled:opacity-40"
            >
              <RefreshCcw className="w-4 h-4"/>
              {baseline ? 'Recalibrate' : 'Calibrate Posture'}
            </button>
          </div>

          {/* Mini stat cards */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-slate-800/70 border border-slate-700/60 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-1">
                <Zap className="w-4 h-4 text-red-400"/>
                <span className="text-xs text-slate-500">Slouches</span>
              </div>
              <p className="text-2xl font-bold text-white">{slouchCount}</p>
            </div>
            <div className="bg-slate-800/70 border border-slate-700/60 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-1">
                <Clock className="w-4 h-4 text-blue-400"/>
                <span className="text-xs text-slate-500">Session</span>
              </div>
              <p className="text-2xl font-bold font-mono text-white">{formatTime(elapsedSeconds)}</p>
            </div>
          </div>

          {/* Good posture ring */}
          {elapsedSeconds > 0 && (
            <div className="bg-slate-800/70 border border-slate-700/60 rounded-xl p-5 flex items-center gap-5">
              <div className="relative w-14 h-14">
                <svg className="w-14 h-14 -rotate-90">
                  <circle cx="28" cy="28" r="22" fill="none" stroke="#1e293b" strokeWidth="5"/>
                  <circle cx="28" cy="28" r="22" fill="none" stroke={goodPercent > 70 ? '#10b981' : goodPercent > 40 ? '#f59e0b' : '#ef4444'}
                    strokeWidth="5" strokeDasharray={`${(goodPercent / 100) * 138} 138`} strokeLinecap="round"/>
                </svg>
                <span className="absolute inset-0 flex items-center justify-center text-xs font-bold">{goodPercent}%</span>
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-200">Good Posture</p>
                <p className="text-xs text-slate-500">{goodSeconds}s of {elapsedSeconds}s tracked</p>
              </div>
            </div>
          )}
        </div>

        {/* RIGHT — Graph */}
        <div className="lg:col-span-2 space-y-5">

          {/* Live Chart */}
          <div className="bg-slate-800/60 border border-slate-700/60 rounded-2xl p-6">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h3 className="text-base font-semibold text-slate-100">Live Head Drop</h3>
                <p className="text-xs text-slate-500">Real-time angular tracking in degrees</p>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="w-3 h-0.5 bg-blue-400 inline-block rounded"/>
                <span className="text-slate-500">drop</span>
                <span className="w-3 h-0.5 bg-red-500 border-dashed inline-block rounded ml-2"/>
                <span className="text-slate-500">threshold</span>
              </div>
            </div>

            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="dropGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false}/>
                  <XAxis dataKey="time" hide/>
                  <YAxis domain={[-5, threshold + 15]} stroke="#334155" fontSize={11}
                    tickFormatter={v => `${v}°`} tickLine={false}/>
                  <Tooltip content={<CustomTooltip/>}/>
                  <ReferenceLine y={threshold} stroke="#ef4444" strokeDasharray="5 3" strokeWidth={1.5}
                    label={{ position: 'right', value: `${threshold}°`, fill: '#ef4444', fontSize: 11 }}/>
                  <ReferenceLine y={0} stroke="#334155" strokeWidth={1}/>
                  <Area type="monotone" dataKey="drop" stroke="#3b82f6" strokeWidth={2.5}
                    fill="url(#dropGrad)" dot={false} isAnimationActive={false}/>
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Instructions / How it works */}
          <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-6">
            <h3 className="text-sm font-semibold text-slate-300 mb-4">How to use PostureFix</h3>
            <div className="grid grid-cols-3 gap-4">
              {[
                { step: '1', title: 'Start Camera', desc: 'Click "Start Camera" to begin face tracking in the background.' },
                { step: '2', title: 'Calibrate', desc: 'Sit upright in your ideal posture and click Calibrate.' },
                { step: '3', title: 'Stay straight!', desc: 'PostureFix will alert you by voice whenever you slouch.' },
              ].map(item => (
                <div key={item.step} className="text-center">
                  <div className="w-8 h-8 rounded-full bg-blue-600/20 text-blue-400 text-sm font-bold flex items-center justify-center mx-auto mb-2">
                    {item.step}
                  </div>
                  <p className="text-sm font-medium text-slate-300 mb-1">{item.title}</p>
                  <p className="text-xs text-slate-500">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>

        </div>
      </main>
    </div>
  );
}
