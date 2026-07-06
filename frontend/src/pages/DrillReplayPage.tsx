import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  InputNumber,
  Progress,
  Row,
  Select,
  Slider,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
  message
} from "antd";
import {
  CaretRightOutlined,
  PauseOutlined,
  ReloadOutlined,
  StepBackwardOutlined,
  StepForwardOutlined
} from "@ant-design/icons";
import dayjs from "dayjs";
import { useTranslation } from "react-i18next";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import {
  alignWellRun,
  listWellRunChannels,
  listWellRunSegments,
  listWellRuns,
  type WellRunAlignedRow,
  type WellRunAlignResponse,
  type WellRunChannelSummary,
  type WellRunResponse,
  type WellRunSegmentResponse
} from "../api/wellRuns";
import { PageHeader, PageShell } from "../components/PageShell";
import { listWarehouses, type DataWarehouseResponse } from "../api/warehouses";
import { useAuth } from "../auth/AuthProvider";

type SoilLayer = {
  name: string;
  top: number;
  bottom: number;
  color: string;
};

const METRIC_KEYS = ["pressure", "vibration", "wob", "rpm", "inclination", "azimuth", "torque"] as const;
type MetricKey = (typeof METRIC_KEYS)[number];
type ChannelSelection = Record<MetricKey, string | null>;

type ReplayFrame = {
  ts: string;
  md: number | null;
  metrics: Record<MetricKey, number | null>;
};

type SegmentInterval = {
  id: string;
  type: string;
  source: string;
  color: string;
  start: number;
  end: number;
};

const METRIC_UNITS: Record<MetricKey, string> = {
  pressure: "psi",
  vibration: "g",
  wob: "kN",
  rpm: "rpm",
  inclination: "deg",
  azimuth: "deg",
  torque: "kN*m"
};

const METRIC_COLORS: Record<MetricKey, string> = {
  pressure: "#d4380d",
  vibration: "#fa8c16",
  wob: "#389e0d",
  rpm: "#0958d9",
  inclination: "#13a8a8",
  azimuth: "#531dab",
  torque: "#7cb305"
};

const METRIC_CANDIDATES: Record<MetricKey, string[]> = {
  pressure: ["standpipe_pressure", "spp", "pressure", "pump_pressure"],
  vibration: ["bit_vibration", "vibration", "shock", "accel", "rms"],
  wob: ["wob", "weight_on_bit"],
  rpm: ["rpm", "rotary_rpm", "bit_rpm", "rotation"],
  inclination: ["inclination", "inc", "hole_angle"],
  azimuth: ["azimuth", "azi", "toolface"],
  torque: ["torque", "rotary_torque"]
};

const SOIL_COLORS = ["#d0a97a", "#b8895f", "#9f7a53", "#7f6548", "#cbb490", "#8e8476"];
const SEGMENT_COLORS = ["#f97316", "#22c55e", "#3b82f6", "#a855f7", "#14b8a6", "#ef4444", "#eab308"];

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function encodeSourceChannel(source: string, channel: string) {
  return `${source}::${channel}`;
}

function decodeSourceChannel(value: string) {
  const idx = value.indexOf("::");
  if (idx <= 0) {
    return { source: "", channel: value };
  }
  return {
    source: value.slice(0, idx),
    channel: value.slice(idx + 2)
  };
}

function formatTs(ts?: string | null) {
  if (!ts) return "-";
  return dayjs(ts).format("MM-DD HH:mm:ss");
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object") {
    return value as Record<string, unknown>;
  }
  return null;
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function parseSoilLayers(details: Record<string, unknown> | undefined): SoilLayer[] {
  const rootKeys = ["geology", "formation", "strata"];
  for (const key of rootKeys) {
    const root = asRecord(details?.[key]);
    const layerList = root?.layers;
    if (!Array.isArray(layerList)) continue;
    const parsed: SoilLayer[] = [];
    layerList.forEach((item, idx) => {
      const layer = asRecord(item);
      if (!layer) return;
      const top = toNumber(layer.top_md ?? layer.top ?? layer.start_md ?? layer.start);
      const bottom = toNumber(layer.bottom_md ?? layer.bottom ?? layer.end_md ?? layer.end);
      if (top === null || bottom === null || bottom <= top) return;
      parsed.push({
        name: String(layer.name ?? layer.type ?? `Layer ${idx + 1}`),
        top,
        bottom,
        color: String(layer.color ?? SOIL_COLORS[idx % SOIL_COLORS.length])
      });
    });
    if (parsed.length) {
      return parsed.sort((a, b) => a.top - b.top);
    }
  }
  return [];
}

function buildFallbackSoilLayers(depthRange: { min: number; max: number }): SoilLayer[] {
  const span = Math.max(1, depthRange.max - depthRange.min);
  const start = depthRange.min;
  return [
    { name: "Soft Clay", top: start, bottom: start + span * 0.2, color: "#c89a6d" },
    { name: "Sandstone", top: start + span * 0.2, bottom: start + span * 0.48, color: "#b17e4f" },
    { name: "Shale", top: start + span * 0.48, bottom: start + span * 0.74, color: "#87705a" },
    { name: "Limestone", top: start + span * 0.74, bottom: start + span, color: "#c4b49a" }
  ];
}

function pickDefaultChannel(options: Array<{ value: string; channelLower: string }>, candidates: string[]) {
  for (const candidate of candidates) {
    const found = options.find((item) => item.channelLower.includes(candidate));
    if (found) return found.value;
  }
  return null;
}

function metricLabel(t: (key: string) => string, key: MetricKey) {
  return t(`replay.metric.${key}`);
}

function colorBySegment(segmentType: string) {
  let hash = 0;
  for (let i = 0; i < segmentType.length; i += 1) {
    hash = (hash * 31 + segmentType.charCodeAt(i)) >>> 0;
  }
  return SEGMENT_COLORS[hash % SEGMENT_COLORS.length];
}

function drawReplayScene(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  frame: ReplayFrame | null,
  depth: number,
  depthRange: { min: number; max: number },
  soilLayers: SoilLayer[],
  phase: number,
  labels: { depthLabel: string; azimuthLabel: string; inclinationLabel: string }
) {
  const top = 26;
  const bottom = height - 24;
  const sceneHeight = bottom - top;
  const centerX = width * 0.5;
  const holeWidth = Math.max(90, width * 0.28);

  ctx.clearRect(0, 0, width, height);

  const bgGradient = ctx.createLinearGradient(0, 0, 0, height);
  bgGradient.addColorStop(0, "#f7fbff");
  bgGradient.addColorStop(1, "#e6edf5");
  ctx.fillStyle = bgGradient;
  ctx.fillRect(0, 0, width, height);

  const minDepth = depthRange.min;
  const depthSpan = Math.max(1, depthRange.max - minDepth);

  soilLayers.forEach((layer) => {
    const y1 = top + ((layer.top - minDepth) / depthSpan) * sceneHeight;
    const y2 = top + ((layer.bottom - minDepth) / depthSpan) * sceneHeight;
    const startY = clamp(y1, top, bottom);
    const endY = clamp(y2, top, bottom);
    if (endY <= startY) return;

    const leftInsetTop = 18 + (startY - top) * 0.08;
    const leftInsetBottom = 18 + (endY - top) * 0.08;
    const rightInsetTop = leftInsetTop;
    const rightInsetBottom = leftInsetBottom;

    ctx.beginPath();
    ctx.moveTo(leftInsetTop, startY);
    ctx.lineTo(width - rightInsetTop, startY);
    ctx.lineTo(width - rightInsetBottom, endY);
    ctx.lineTo(leftInsetBottom, endY);
    ctx.closePath();
    ctx.fillStyle = layer.color;
    ctx.globalAlpha = 0.56;
    ctx.fill();
    ctx.globalAlpha = 1;

    ctx.fillStyle = "rgba(30, 41, 59, 0.65)";
    ctx.font = "12px sans-serif";
    ctx.fillText(layer.name, leftInsetTop + 8, startY + 14);
  });

  const tubeGradient = ctx.createLinearGradient(centerX - holeWidth / 2, 0, centerX + holeWidth / 2, 0);
  tubeGradient.addColorStop(0, "rgba(24, 32, 44, 0.6)");
  tubeGradient.addColorStop(0.5, "rgba(45, 58, 76, 0.72)");
  tubeGradient.addColorStop(1, "rgba(24, 32, 44, 0.6)");
  ctx.fillStyle = tubeGradient;
  ctx.fillRect(centerX - holeWidth / 2, top, holeWidth, sceneHeight);

  ctx.strokeStyle = "rgba(120, 144, 168, 0.75)";
  ctx.lineWidth = 2;
  ctx.strokeRect(centerX - holeWidth / 2, top, holeWidth, sceneHeight);

  const vibration = Math.abs(frame?.metrics.vibration ?? 0);
  const pressure = Math.abs(frame?.metrics.pressure ?? 0);
  const rpm = Math.abs(frame?.metrics.rpm ?? 0);
  const inclination = frame?.metrics.inclination ?? 0;
  const azimuth = frame?.metrics.azimuth ?? 0;

  const vibrationFactor = clamp(vibration / 15, 0, 1);
  const pressureFactor = clamp(pressure / 6000, 0, 1);
  const rpmFactor = clamp(rpm / 220, 0, 1);
  const depthRatio = clamp((depth - minDepth) / depthSpan, 0, 1);

  const pathOffset = Math.sin((inclination * Math.PI) / 180) * depthRatio * 78;
  const azimuthOffset = Math.cos((azimuth * Math.PI) / 180) * 8;
  const jitter = Math.sin(phase * 8.5) * vibrationFactor * 7;
  const bitX = centerX + pathOffset + azimuthOffset + jitter;
  const bitY = top + depthRatio * sceneHeight;

  const stringGradient = ctx.createLinearGradient(bitX, top, bitX, bitY);
  stringGradient.addColorStop(0, "#d9e3ef");
  stringGradient.addColorStop(1, "#8ea1b8");
  ctx.strokeStyle = stringGradient;
  ctx.lineWidth = 10;
  ctx.beginPath();
  ctx.moveTo(centerX, top - 8);
  ctx.lineTo(bitX, bitY - 26);
  ctx.stroke();

  ctx.save();
  ctx.translate(bitX, bitY);
  ctx.rotate((phase * (0.24 + rpmFactor * 1.5)) + (azimuth * Math.PI) / 720);

  if (pressureFactor > 0.1) {
    ctx.fillStyle = `rgba(214, 67, 33, ${0.08 + pressureFactor * 0.2})`;
    ctx.beginPath();
    ctx.arc(0, 4, 32 + pressureFactor * 22, 0, Math.PI * 2);
    ctx.fill();
  }

  const bodyGradient = ctx.createLinearGradient(-14, -24, 14, 24);
  bodyGradient.addColorStop(0, "#f9fbff");
  bodyGradient.addColorStop(0.4, "#b7c4d5");
  bodyGradient.addColorStop(1, "#6b7f96");
  ctx.fillStyle = bodyGradient;
  ctx.beginPath();
  ctx.ellipse(0, -20, 11, 5, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillRect(-11, -20, 22, 30);

  const coneGradient = ctx.createLinearGradient(0, 8, 0, 40);
  coneGradient.addColorStop(0, "#d7e0ea");
  coneGradient.addColorStop(1, "#4f647c");
  ctx.fillStyle = coneGradient;
  ctx.beginPath();
  ctx.moveTo(-12, 10);
  ctx.lineTo(12, 10);
  ctx.lineTo(0, 38);
  ctx.closePath();
  ctx.fill();

  ctx.strokeStyle = "rgba(44, 62, 82, 0.7)";
  ctx.lineWidth = 2;
  for (let i = 0; i < 6; i += 1) {
    const toothAngle = (i / 6) * Math.PI * 2;
    const tx = Math.cos(toothAngle) * 9;
    const ty = Math.sin(toothAngle) * 4 + 12;
    ctx.beginPath();
    ctx.moveTo(tx, ty);
    ctx.lineTo(tx * 0.35, 30);
    ctx.stroke();
  }
  ctx.restore();

  ctx.strokeStyle = "#1f6feb";
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(bitX, bitY);
  const arrowLength = 36;
  const azimuthRad = (azimuth * Math.PI) / 180;
  const ax = bitX + Math.sin(azimuthRad) * arrowLength;
  const ay = bitY - Math.cos(azimuthRad) * arrowLength;
  ctx.lineTo(ax, ay);
  ctx.stroke();

  ctx.fillStyle = "#1f6feb";
  ctx.beginPath();
  ctx.arc(ax, ay, 4, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = "rgba(30, 41, 59, 0.75)";
  ctx.font = "13px sans-serif";
  ctx.fillText(`${labels.depthLabel}: ${depth.toFixed(1)} m`, 18, 18);
  ctx.fillText(`${labels.inclinationLabel}: ${inclination.toFixed(1)} deg`, width - 188, 18);
  ctx.fillText(`${labels.azimuthLabel}: ${azimuth.toFixed(1)} deg`, width - 188, 36);
}

type DrillSceneProps = {
  frame: ReplayFrame | null;
  depth: number;
  depthRange: { min: number; max: number };
  soilLayers: SoilLayer[];
  playing: boolean;
  labels: { depthLabel: string; azimuthLabel: string; inclinationLabel: string };
};

function DrillSceneCanvas({ frame, depth, depthRange, soilLayers, playing, labels }: DrillSceneProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frameRef = useRef<ReplayFrame | null>(frame);
  const depthRef = useRef(depth);
  const rangeRef = useRef(depthRange);
  const soilRef = useRef(soilLayers);
  const playingRef = useRef(playing);
  const labelsRef = useRef(labels);

  useEffect(() => {
    frameRef.current = frame;
  }, [frame]);

  useEffect(() => {
    depthRef.current = depth;
  }, [depth]);

  useEffect(() => {
    rangeRef.current = depthRange;
  }, [depthRange]);

  useEffect(() => {
    soilRef.current = soilLayers;
  }, [soilLayers]);

  useEffect(() => {
    playingRef.current = playing;
  }, [playing]);

  useEffect(() => {
    labelsRef.current = labels;
  }, [labels]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let phase = 0;

    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const width = Math.max(320, Math.floor(rect.width));
      const height = 470;
      const dpr = window.devicePixelRatio || 1;

      if (canvas.width !== Math.floor(width * dpr) || canvas.height !== Math.floor(height * dpr)) {
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      phase += playingRef.current ? 0.12 : 0.04;
      drawReplayScene(
        ctx,
        width,
        height,
        frameRef.current,
        depthRef.current,
        rangeRef.current,
        soilRef.current,
        phase,
        labelsRef.current
      );
      raf = window.requestAnimationFrame(draw);
    };

    raf = window.requestAnimationFrame(draw);
    return () => {
      window.cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        width: "100%",
        height: 470,
        borderRadius: 14,
        border: "1px solid #d9e2ef",
        background: "linear-gradient(160deg, #f7fbff 0%, #ebf2fb 100%)"
      }}
    />
  );
}

function DrillSceneVector({ frame, depth, depthRange, soilLayers, playing, labels }: DrillSceneProps) {
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setPhase((prev) => prev + (playing ? 1 : 0.25));
    }, 80);
    return () => {
      window.clearInterval(timer);
    };
  }, [playing]);

  const minDepth = depthRange.min;
  const span = Math.max(1, depthRange.max - minDepth);
  const depthRatio = clamp((depth - minDepth) / span, 0, 1);

  const vibration = Math.abs(frame?.metrics.vibration ?? 0);
  const pressure = Math.abs(frame?.metrics.pressure ?? 0);
  const rpm = Math.abs(frame?.metrics.rpm ?? 0);
  const inclination = frame?.metrics.inclination ?? 0;
  const azimuth = frame?.metrics.azimuth ?? 0;

  const vibrationFactor = clamp(vibration / 15, 0, 1);
  const pressureFactor = clamp(pressure / 6000, 0, 1);
  const rpmFactor = clamp(rpm / 220, 0, 1);

  const holeTop = 44;
  const holeBottom = 432;
  const holeHeight = holeBottom - holeTop;
  const centerX = 300;
  const holeWidth = 126;

  const lateral = Math.sin((inclination * Math.PI) / 180) * depthRatio * 72;
  const jitter = Math.sin(phase * 0.34) * vibrationFactor * 9;
  const bitX = centerX + lateral + jitter;
  const bitY = holeTop + depthRatio * holeHeight;
  const spinPhase = phase * (0.32 + rpmFactor * 2.4);
  const stripeShift = ((spinPhase * 10) % 16) - 8;

  const azimuthRad = (azimuth * Math.PI) / 180;
  const arrowLen = 38;
  const arrowX = bitX + Math.sin(azimuthRad) * arrowLen;
  const arrowY = bitY - Math.cos(azimuthRad) * arrowLen;

  const haloR = 14 + pressureFactor * 22;
  const haloOpacity = 0.07 + pressureFactor * 0.22;

  return (
    <div
      style={{
        width: "100%",
        height: 470,
        borderRadius: 14,
        border: "1px solid #d9e2ef",
        background: "linear-gradient(160deg, #f7fbff 0%, #ebf2fb 100%)",
        overflow: "hidden"
      }}
    >
      <svg viewBox="0 0 600 470" width="100%" height="100%" preserveAspectRatio="none">
        <defs>
          <linearGradient id="wv-bg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f8fbff" />
            <stop offset="100%" stopColor="#e6edf7" />
          </linearGradient>
          <linearGradient id="wv-hole" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#172233" stopOpacity="0.64" />
            <stop offset="50%" stopColor="#2f4560" stopOpacity="0.76" />
            <stop offset="100%" stopColor="#172233" stopOpacity="0.64" />
          </linearGradient>
          <linearGradient id="wv-string" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#dae4f1" />
            <stop offset="100%" stopColor="#8fa4bc" />
          </linearGradient>
          <linearGradient id="wv-bit" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#f7fbff" />
            <stop offset="60%" stopColor="#a9bccf" />
            <stop offset="100%" stopColor="#6f859d" />
          </linearGradient>
        </defs>

        <rect x={0} y={0} width={600} height={470} fill="url(#wv-bg)" />

        {soilLayers.map((layer, idx) => {
          const y1 = holeTop + clamp((layer.top - minDepth) / span, 0, 1) * holeHeight;
          const y2 = holeTop + clamp((layer.bottom - minDepth) / span, 0, 1) * holeHeight;
          const h = Math.max(1, y2 - y1);
          return (
            <g key={`${layer.name}-${idx}`}>
              <rect x={32} y={y1} width={536} height={h} fill={layer.color} fillOpacity={0.55} />
              <text x={44} y={y1 + 14} fill="rgba(30,41,59,0.72)" fontSize={12}>
                {layer.name}
              </text>
            </g>
          );
        })}

        <rect
          x={centerX - holeWidth / 2}
          y={holeTop}
          width={holeWidth}
          height={holeHeight}
          fill="url(#wv-hole)"
          stroke="rgba(120,144,168,0.78)"
          strokeWidth={2}
          rx={8}
        />

        <line x1={centerX} y1={holeTop - 10} x2={bitX} y2={bitY - 26} stroke="url(#wv-string)" strokeWidth={10} />

        <g transform={`translate(${bitX}, ${bitY})`}>
          <circle r={haloR} fill="#d64321" opacity={haloOpacity} />
          <ellipse cx={0} cy={-18} rx={11} ry={6} fill="url(#wv-bit)" />
          <rect x={-11} y={-18} width={22} height={30} fill="url(#wv-bit)" />
          <line x1={-9 + stripeShift} y1={-18} x2={-5 + stripeShift} y2={12} stroke="rgba(70,92,116,0.58)" strokeWidth={1.8} />
          <line x1={-1 + stripeShift} y1={-18} x2={3 + stripeShift} y2={12} stroke="rgba(70,92,116,0.58)" strokeWidth={1.8} />
          <line x1={7 + stripeShift} y1={-18} x2={11 + stripeShift} y2={12} stroke="rgba(70,92,116,0.58)" strokeWidth={1.8} />
          <polygon points="-12,12 12,12 0,38" fill="#5f738c" />
          {Array.from({ length: 6 }).map((_, idx) => {
            const angle = spinPhase + (idx / 6) * Math.PI * 2;
            const x = Math.sin(angle) * 9;
            const y = 13 + Math.cos(angle) * 2.8;
            const frontFactor = (Math.cos(angle) + 1) * 0.5;
            const r = 1.4 + frontFactor * 1.1;
            const opacity = 0.35 + frontFactor * 0.55;
            return <circle key={idx} cx={x} cy={y} r={r} fill={`rgba(44,62,82,${opacity.toFixed(3)})`} />;
          })}
        </g>

        <line x1={bitX} y1={bitY} x2={arrowX} y2={arrowY} stroke="#1f6feb" strokeWidth={3} />
        <circle cx={arrowX} cy={arrowY} r={4} fill="#1f6feb" />

        <text x={18} y={22} fill="rgba(30,41,59,0.78)" fontSize={13}>
          {labels.depthLabel}: {depth.toFixed(1)} m
        </text>
        <text x={398} y={22} fill="rgba(30,41,59,0.78)" fontSize={13}>
          {labels.inclinationLabel}: {inclination.toFixed(1)} deg
        </text>
        <text x={398} y={40} fill="rgba(30,41,59,0.78)" fontSize={13}>
          {labels.azimuthLabel}: {azimuth.toFixed(1)} deg
        </text>
      </svg>
    </div>
  );
}

function DrillSceneThree({
  frame,
  depth,
  depthRange,
  soilLayers,
  playing,
  onFallback
}: DrillSceneProps & { onFallback: () => void }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const frameRef = useRef<ReplayFrame | null>(frame);
  const depthRef = useRef(depth);
  const depthRangeRef = useRef(depthRange);
  const soilRef = useRef(soilLayers);
  const playingRef = useRef(playing);

  useEffect(() => {
    frameRef.current = frame;
  }, [frame]);

  useEffect(() => {
    depthRef.current = depth;
  }, [depth]);

  useEffect(() => {
    depthRangeRef.current = depthRange;
  }, [depthRange]);

  useEffect(() => {
    soilRef.current = soilLayers;
  }, [soilLayers]);

  useEffect(() => {
    playingRef.current = playing;
  }, [playing]);

  useEffect(() => {
    let cancelled = false;
    let raf = 0;
    let renderer: any = null;
    let scene: any = null;
    let contextLostHandler: ((event: Event) => void) | null = null;
    let cleanupResize: (() => void) | null = null;
    let healthTimer = 0;
    let renderedFrames = 0;

    const container = containerRef.current;
    if (!container) {
      onFallback();
      return;
    }
    if (typeof window === "undefined" || !("WebGLRenderingContext" in window)) {
      onFallback();
      return;
    }

    const setup = async () => {
      try {
        const THREE = await import("three");
        if (cancelled || !containerRef.current) return;

        scene = new THREE.Scene();
        scene.background = new THREE.Color("#edf3fa");

        const width = Math.max(320, container.clientWidth || 320);
        const height = 470;
        const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 2000);
        camera.position.set(96, 34, 134);
        camera.lookAt(0, -40, 0);

        try {
          renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
        } catch {
          renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true, powerPreference: "high-performance" });
        }
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.setSize(width, height);
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        contextLostHandler = (event: Event) => {
          event.preventDefault();
          onFallback();
        };
        renderer.domElement.addEventListener("webglcontextlost", contextLostHandler, false);
        container.innerHTML = "";
        container.appendChild(renderer.domElement);

        const ambient = new THREE.AmbientLight(0xffffff, 0.92);
        scene.add(ambient);
        const lightA = new THREE.DirectionalLight(0xffffff, 0.9);
        lightA.position.set(60, 120, 80);
        scene.add(lightA);
        const lightB = new THREE.DirectionalLight(0xb9d4ff, 0.45);
        lightB.position.set(-120, 50, -90);
        scene.add(lightB);

        const pitBase = new THREE.Mesh(
          new THREE.BoxGeometry(260, 236, 260),
          new THREE.MeshStandardMaterial({ color: "#d7e2ef", roughness: 0.96, metalness: 0.04 })
        );
        pitBase.position.set(0, -78, 0);
        scene.add(pitBase);

        const boreholeShell = new THREE.Mesh(
          new THREE.CylinderGeometry(22, 22, 236, 40, 1, true),
          new THREE.MeshStandardMaterial({
            color: "#36495f",
            roughness: 0.22,
            metalness: 0.28,
            transparent: true,
            opacity: 0.36,
            side: THREE.DoubleSide
          })
        );
        boreholeShell.position.set(0, -78, 0);
        scene.add(boreholeShell);

        const topCap = new THREE.Mesh(
          new THREE.RingGeometry(22, 52, 64),
          new THREE.MeshStandardMaterial({ color: "#9eb1c7", roughness: 0.54, metalness: 0.1, side: THREE.DoubleSide })
        );
        topCap.rotation.x = -Math.PI / 2;
        topCap.position.set(0, 40, 0);
        scene.add(topCap);

        const soilGroup = new THREE.Group();
        scene.add(soilGroup);

        const stringMat = new THREE.MeshStandardMaterial({ color: "#d6e2f0", roughness: 0.22, metalness: 0.84 });
        const drillString = new THREE.Mesh(new THREE.CylinderGeometry(2.3, 2.7, 160, 16), stringMat);
        drillString.position.set(0, -40, 0);
        scene.add(drillString);

        const bitGroup = new THREE.Group();
        scene.add(bitGroup);

        const bitBody = new THREE.Mesh(
          new THREE.CylinderGeometry(6.5, 7.5, 22, 24),
          new THREE.MeshStandardMaterial({ color: "#a8bbce", roughness: 0.18, metalness: 0.72 })
        );
        bitBody.position.y = -8;
        bitGroup.add(bitBody);

        const bitCone = new THREE.Mesh(
          new THREE.ConeGeometry(9.8, 18, 28),
          new THREE.MeshStandardMaterial({ color: "#7e96af", roughness: 0.26, metalness: 0.62 })
        );
        bitCone.position.y = -25;
        bitGroup.add(bitCone);

        for (let i = 0; i < 12; i += 1) {
          const angle = (i / 12) * Math.PI * 2;
          const tooth = new THREE.Mesh(
            new THREE.ConeGeometry(1.3, 4.8, 8),
            new THREE.MeshStandardMaterial({ color: "#5f738c", roughness: 0.2, metalness: 0.66 })
          );
          tooth.position.set(Math.cos(angle) * 7.8, -32.5, Math.sin(angle) * 7.8);
          tooth.rotation.z = Math.PI;
          tooth.rotation.y = angle;
          bitGroup.add(tooth);
        }

        const pressureHalo = new THREE.Mesh(
          new THREE.SphereGeometry(16, 20, 20),
          new THREE.MeshBasicMaterial({
            color: "#ef5a36",
            transparent: true,
            opacity: 0.08,
            blending: THREE.AdditiveBlending,
            depthWrite: false
          })
        );
        pressureHalo.position.y = -18;
        bitGroup.add(pressureHalo);

        const directionArrow = new THREE.ArrowHelper(new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 0, 0), 20, 0x1f6feb, 5, 2.4);
        bitGroup.add(directionArrow);

        const tmpDir = new THREE.Vector3(0, -1, 0);
        const depthToWorldY = (value: number) => {
          const range = depthRangeRef.current;
          const span = Math.max(1, range.max - range.min);
          const ratio = clamp((value - range.min) / span, 0, 1);
          return 40 - ratio * 236;
        };

        const rebuildSoilLayers = () => {
          while (soilGroup.children.length) {
            const child = soilGroup.children.pop();
            if (!child) break;
            soilGroup.remove(child);
          }
          const minDepth = depthRangeRef.current.min;
          const maxDepth = depthRangeRef.current.max;
          const depthSpan = Math.max(1, maxDepth - minDepth);
          soilRef.current.forEach((layer) => {
            const layerTop = clamp(layer.top, minDepth, maxDepth);
            const layerBottom = clamp(layer.bottom, minDepth, maxDepth);
            if (layerBottom <= layerTop) return;
            const heightValue = ((layerBottom - layerTop) / depthSpan) * 236;
            const yCenter = depthToWorldY(layerTop) - heightValue * 0.5;
            const matLeft = new THREE.MeshStandardMaterial({
              color: layer.color,
              transparent: true,
              opacity: 0.66,
              roughness: 0.88,
              metalness: 0.03
            });
            const matRight = matLeft.clone();
            const sideGeo = new THREE.BoxGeometry(56, Math.max(2.2, heightValue), 110);
            const leftSide = new THREE.Mesh(sideGeo, matLeft);
            leftSide.position.set(-72, yCenter, 0);
            soilGroup.add(leftSide);
            const rightSide = new THREE.Mesh(sideGeo.clone(), matRight);
            rightSide.position.set(72, yCenter, 0);
            soilGroup.add(rightSide);
          });
        };
        rebuildSoilLayers();

        let phase = 0;
        const animate = () => {
          if (cancelled) return;
          const gl: WebGLRenderingContext | WebGL2RenderingContext | null =
            typeof renderer?.getContext === "function" ? renderer.getContext() : null;
          if (gl && typeof gl.isContextLost === "function" && gl.isContextLost()) {
            cancelled = true;
            onFallback();
            return;
          }
          phase += playingRef.current ? 0.11 : 0.04;

          const frameValue = frameRef.current;
          const depthValue = depthRef.current;
          const range = depthRangeRef.current;
          const span = Math.max(1, range.max - range.min);
          const depthRatio = clamp((depthValue - range.min) / span, 0, 1);
          const y = 40 - depthRatio * 236;

          const vibration = Math.abs(frameValue?.metrics.vibration ?? 0);
          const pressure = Math.abs(frameValue?.metrics.pressure ?? 0);
          const rpm = Math.abs(frameValue?.metrics.rpm ?? 0);
          const inclination = frameValue?.metrics.inclination ?? 0;
          const azimuth = frameValue?.metrics.azimuth ?? 0;

          const vibrationFactor = clamp(vibration / 15, 0, 1);
          const pressureFactor = clamp(pressure / 6000, 0, 1);
          const rpmFactor = clamp(rpm / 220, 0, 1);

          const incRad = (inclination * Math.PI) / 180;
          const aziRad = (azimuth * Math.PI) / 180;
          const lateral = Math.sin(incRad) * depthRatio * 16;
          const jitterX = Math.sin(phase * 8.2) * vibrationFactor * 2.6;
          const jitterZ = Math.cos(phase * 8.6) * vibrationFactor * 2.3;
          const bitX = Math.cos(aziRad) * lateral + jitterX;
          const bitZ = Math.sin(aziRad) * lateral + jitterZ;

          bitGroup.position.set(bitX, y, bitZ);
          bitGroup.rotation.y += 0.02 + rpmFactor * (playingRef.current ? 0.32 : 0.08);

          pressureHalo.scale.setScalar(1 + pressureFactor * 2.7);
          const haloMat = pressureHalo.material as any;
          haloMat.opacity = 0.06 + pressureFactor * 0.28;

          const stringLength = Math.max(18, 40 - y);
          drillString.scale.set(1, stringLength / 160, 1);
          drillString.position.set(bitX * 0.38, 40 - stringLength * 0.5, bitZ * 0.38);
          drillString.rotation.set(0, 0, 0);

          tmpDir.set(Math.sin(aziRad), -Math.max(0.18, Math.cos(incRad)), Math.cos(aziRad)).normalize();
          directionArrow.setDirection(tmpDir);
          directionArrow.setLength(18, 5, 2.8);

          renderer.render(scene, camera);
          renderedFrames += 1;
          raf = window.requestAnimationFrame(animate);
        };

        const handleResize = () => {
          if (!containerRef.current || !renderer) return;
          const w = Math.max(320, containerRef.current.clientWidth || 320);
          const h = 470;
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
          renderer.setSize(w, h);
        };

        window.addEventListener("resize", handleResize);
        cleanupResize = () => window.removeEventListener("resize", handleResize);

        const soilSyncTimer = window.setInterval(rebuildSoilLayers, 1200);
        const prevCleanup = cleanupResize;
        cleanupResize = () => {
          window.clearInterval(soilSyncTimer);
          prevCleanup?.();
        };

        healthTimer = window.setTimeout(() => {
          if (!cancelled && renderedFrames < 2) {
            cancelled = true;
            onFallback();
          }
        }, 2500);

        animate();
      } catch (err) {
        onFallback();
      }
    };

    void setup();

    return () => {
      cancelled = true;
      if (healthTimer) window.clearTimeout(healthTimer);
      if (raf) window.cancelAnimationFrame(raf);
      cleanupResize?.();
      if (renderer) {
        if (contextLostHandler) {
          renderer.domElement.removeEventListener("webglcontextlost", contextLostHandler as EventListener);
        }
        if (scene && typeof scene.traverse === "function") {
          scene.traverse((obj: any) => {
            if (obj?.geometry?.dispose) obj.geometry.dispose();
            if (obj?.material) {
              if (Array.isArray(obj.material)) {
                obj.material.forEach((mat: any) => mat?.dispose?.());
              } else if (obj.material.dispose) {
                obj.material.dispose();
              }
            }
          });
        }
        if (typeof renderer.forceContextLoss === "function") {
          renderer.forceContextLoss();
        }
        renderer.dispose();
      }
      if (containerRef.current) {
        containerRef.current.innerHTML = "";
      }
    };
  }, [onFallback]);

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: 470,
        borderRadius: 14,
        overflow: "hidden",
        border: "1px solid #d9e2ef",
        background: "linear-gradient(160deg, #f7fbff 0%, #ebf2fb 100%)"
      }}
    />
  );
}

function DrillScene(props: DrillSceneProps) {
  return <DrillSceneVector {...props} />;
}

export function DrillReplayPage() {
  const { me } = useAuth();
  const { t } = useTranslation();
  const tenantReady = Boolean(me?.tenant_id);

  const [warehouses, setWarehouses] = useState<DataWarehouseResponse[]>([]);
  const [warehouseId, setWarehouseId] = useState<string | null>(null);
  const [wellRuns, setWellRuns] = useState<WellRunResponse[]>([]);
  const [wellRunId, setWellRunId] = useState<string | null>(null);

  const [channels, setChannels] = useState<WellRunChannelSummary[]>([]);
  const [segments, setSegments] = useState<WellRunSegmentResponse[]>([]);
  const [segmentTypes, setSegmentTypes] = useState<string[]>([]);

  const [rows, setRows] = useState<WellRunAlignedRow[]>([]);
  const [loadingMeta, setLoadingMeta] = useState(false);
  const [loadingReplay, setLoadingReplay] = useState(false);

  const [stepSeconds, setStepSeconds] = useState(2);
  const [maxRows, setMaxRows] = useState(6000);

  const [playing, setPlaying] = useState(false);
  const [playhead, setPlayhead] = useState(0);
  const [speed, setSpeed] = useState(1);
  const carryRef = useRef(0);

  const [channelMap, setChannelMap] = useState<ChannelSelection>({
    pressure: null,
    vibration: null,
    wob: null,
    rpm: null,
    inclination: null,
    azimuth: null,
    torque: null
  });

  const selectedWellRun = useMemo(
    () => wellRuns.find((run) => run.id === wellRunId) ?? null,
    [wellRuns, wellRunId]
  );

  const channelOptions = useMemo(
    () =>
      channels.map((item) => {
        const value = encodeSourceChannel(item.source, item.channel);
        return {
          value,
          channelLower: item.channel.toLowerCase(),
          label: `${item.source}/${item.channel} (${item.count})`
        };
      }),
    [channels]
  );

  const availableSegmentTypes = useMemo(
    () => Array.from(new Set(segments.map((segment) => segment.segment_type))).sort(),
    [segments]
  );

  const frames = useMemo<ReplayFrame[]>(() => {
    return rows
      .filter((row) => Boolean(row.ts))
      .map((row) => {
        const metrics = METRIC_KEYS.reduce<Record<MetricKey, number | null>>((acc, key) => {
          const value = row.values?.[key]?.value;
          acc[key] = typeof value === "number" && Number.isFinite(value) ? value : null;
          return acc;
        }, {} as Record<MetricKey, number | null>);

        return {
          ts: String(row.ts),
          md: typeof row.md === "number" && Number.isFinite(row.md) ? row.md : null,
          metrics
        };
      })
      .sort((a, b) => a.ts.localeCompare(b.ts));
  }, [rows]);

  const depthRange = useMemo(() => {
    let min = Number.POSITIVE_INFINITY;
    let max = Number.NEGATIVE_INFINITY;
    frames.forEach((frame) => {
      if (typeof frame.md === "number") {
        min = Math.min(min, frame.md);
        max = Math.max(max, frame.md);
      }
    });
    if (!Number.isFinite(min) || !Number.isFinite(max)) {
      return { min: 0, max: Math.max(1, frames.length * 0.35) };
    }
    if (max <= min) {
      return { min, max: min + 1 };
    }
    return { min, max };
  }, [frames]);

  const soilLayers = useMemo(() => {
    const parsed = parseSoilLayers(selectedWellRun?.details);
    if (!parsed.length) {
      return buildFallbackSoilLayers(depthRange);
    }
    return parsed;
  }, [selectedWellRun, depthRange]);

  const currentIndex = useMemo(() => {
    if (!frames.length) return 0;
    return clamp(playhead, 0, frames.length - 1);
  }, [frames.length, playhead]);

  const currentFrame = useMemo(() => {
    if (!frames.length) return null;
    return frames[currentIndex] ?? null;
  }, [frames, currentIndex]);

  const progressPercent = useMemo(() => {
    if (frames.length <= 1) return 0;
    return (currentIndex / (frames.length - 1)) * 100;
  }, [currentIndex, frames.length]);

  const currentDepth = useMemo(() => {
    if (!currentFrame) return depthRange.min;
    if (typeof currentFrame.md === "number") return currentFrame.md;
    return depthRange.min + ((depthRange.max - depthRange.min) * progressPercent) / 100;
  }, [currentFrame, depthRange, progressPercent]);

  const metricRanges = useMemo(() => {
    const ranges = METRIC_KEYS.reduce<Record<MetricKey, { min: number; max: number }>>((acc, key) => {
      acc[key] = { min: Number.POSITIVE_INFINITY, max: Number.NEGATIVE_INFINITY };
      return acc;
    }, {} as Record<MetricKey, { min: number; max: number }>);

    frames.forEach((frame) => {
      METRIC_KEYS.forEach((key) => {
        const value = frame.metrics[key];
        if (typeof value !== "number") return;
        ranges[key].min = Math.min(ranges[key].min, value);
        ranges[key].max = Math.max(ranges[key].max, value);
      });
    });

    METRIC_KEYS.forEach((key) => {
      const item = ranges[key];
      if (!Number.isFinite(item.min) || !Number.isFinite(item.max)) {
        ranges[key] = { min: 0, max: 1 };
      } else if (item.max <= item.min) {
        ranges[key] = { min: item.min, max: item.min + 1 };
      }
    });

    return ranges;
  }, [frames]);

  const dataCoverage = useMemo(() => {
    if (!frames.length) return 0;
    let present = 0;
    let total = 0;
    frames.forEach((frame) => {
      METRIC_KEYS.forEach((key) => {
        total += 1;
        if (typeof frame.metrics[key] === "number") present += 1;
      });
    });
    if (!total) return 0;
    return present / total;
  }, [frames]);

  const trendData = useMemo(() => {
    if (!frames.length) return [];
    const start = Math.max(0, currentIndex - 500);
    const end = currentIndex + 1;
    const raw = frames.slice(start, end);
    const stride = Math.max(1, Math.floor(raw.length / 220));
    const sampled = raw.filter((_, idx) => idx % stride === 0 || idx === raw.length - 1);
    return sampled.map((frame, idx) => ({
      index: start + idx * stride,
      tms: dayjs(frame.ts).valueOf(),
      ts: frame.ts,
      md: frame.md,
      pressure: frame.metrics.pressure,
      vibration: frame.metrics.vibration,
      rpm: frame.metrics.rpm,
      wob: frame.metrics.wob
    }));
  }, [frames, currentIndex]);

  const segmentTimeline = useMemo<SegmentInterval[]>(() => {
    return segments.reduce<SegmentInterval[]>((acc, segment) => {
      if (!segment.start_ts || !segment.end_ts) return acc;
      const start = dayjs(segment.start_ts).valueOf();
      const end = dayjs(segment.end_ts).valueOf();
      if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return acc;
      acc.push({
        id: segment.id,
        type: segment.segment_type,
        source: segment.source,
        color: colorBySegment(segment.segment_type),
        start,
        end
      });
      return acc;
    }, []);
  }, [segments]);

  const trendSegments = useMemo(() => {
    if (!trendData.length) return [];
    const start = trendData[0].tms;
    const end = trendData[trendData.length - 1].tms;
    return segmentTimeline
      .filter((segment) => (segment.end ?? 0) >= start && (segment.start ?? 0) <= end)
      .map((segment) => ({
        ...segment,
        x1: Math.max(start, segment.start ?? start),
        x2: Math.min(end, segment.end ?? end)
      }));
  }, [segmentTimeline, trendData]);

  const trajectoryData = useMemo(() => {
    if (!frames.length) return [];
    let x = 0;
    let y = 0;
    let prevMd = frames[0].md ?? depthRange.min;
    return frames.map((frame, idx) => {
      const md = frame.md ?? prevMd + 0.25;
      const deltaMd = idx === 0 ? 0 : Math.max(0, md - prevMd);
      prevMd = md;
      const inc = ((frame.metrics.inclination ?? 0) * Math.PI) / 180;
      const azi = ((frame.metrics.azimuth ?? 0) * Math.PI) / 180;
      const horizontal = deltaMd * Math.sin(inc);
      x += horizontal * Math.sin(azi);
      y += horizontal * Math.cos(azi);
      return {
        index: idx,
        ts: frame.ts,
        tms: dayjs(frame.ts).valueOf(),
        md,
        x,
        y
      };
    });
  }, [frames, depthRange.min]);

  const trajectoryWindowData = useMemo(() => {
    if (!trajectoryData.length) return [];
    const start = Math.max(0, currentIndex - 800);
    const end = currentIndex + 1;
    const raw = trajectoryData.slice(start, end);
    const stride = Math.max(1, Math.floor(raw.length / 260));
    return raw.filter((_, idx) => idx % stride === 0 || idx === raw.length - 1);
  }, [trajectoryData, currentIndex]);

  const currentTrajectoryPoint = useMemo(() => {
    if (!trajectoryData.length) return null;
    return trajectoryData[currentIndex] ?? trajectoryData[trajectoryData.length - 1];
  }, [trajectoryData, currentIndex]);

  const activeSegment = useMemo(() => {
    if (!currentFrame) return null;
    const ts = dayjs(currentFrame.ts).valueOf();
    return segmentTimeline.find((segment) => {
      return ts >= segment.start && ts <= segment.end;
    }) ?? null;
  }, [currentFrame, segmentTimeline]);

  const mappedCount = useMemo(
    () => METRIC_KEYS.filter((key) => Boolean(channelMap[key])).length,
    [channelMap]
  );

  useEffect(() => {
    if (!tenantReady) return;
    const run = async () => {
      setLoadingMeta(true);
      try {
        const warehouseData = await listWarehouses();
        setWarehouses(warehouseData);
        if (!warehouseId && warehouseData.length) {
          setWarehouseId(warehouseData[0].id);
        }
      } catch (err) {
        message.error(t("replay.metaLoadFail"));
      } finally {
        setLoadingMeta(false);
      }
    };
    void run();
  }, [tenantReady]);

  useEffect(() => {
    if (!tenantReady) return;
    const run = async () => {
      setLoadingMeta(true);
      try {
        const params = warehouseId ? { warehouse_id: warehouseId, limit: 300 } : { limit: 300 };
        const runs = await listWellRuns(params);
        setWellRuns(runs);
        if (runs.length === 0) {
          setWellRunId(null);
          return;
        }
        if (!runs.some((item) => item.id === wellRunId)) {
          setWellRunId(runs[0].id);
        }
      } catch (err) {
        message.error(t("replay.metaLoadFail"));
      } finally {
        setLoadingMeta(false);
      }
    };
    void run();
  }, [tenantReady, warehouseId]);

  useEffect(() => {
    if (!wellRunId) {
      setChannels([]);
      setSegments([]);
      setRows([]);
      setSegmentTypes([]);
      setPlayhead(0);
      setPlaying(false);
      return;
    }

    const run = async () => {
      setLoadingMeta(true);
      try {
        const [channelData, segmentData] = await Promise.all([
          listWellRunChannels(wellRunId, 1200),
          listWellRunSegments(wellRunId, { limit: 2500 })
        ]);
        setChannels(channelData);
        setSegments(segmentData);
        const segmentTypeSet = Array.from(new Set(segmentData.map((segment) => segment.segment_type))).sort();
        setSegmentTypes(segmentTypeSet);
      } catch (err) {
        message.error(t("replay.metaLoadFail"));
      } finally {
        setLoadingMeta(false);
      }
    };

    void run();
  }, [wellRunId]);

  useEffect(() => {
    if (!channelOptions.length) return;
    const validValues = new Set(channelOptions.map((item) => item.value));
    setChannelMap((prev) => {
      const next: ChannelSelection = { ...prev };
      METRIC_KEYS.forEach((key) => {
        if (next[key] && validValues.has(next[key] ?? "")) return;
        next[key] = pickDefaultChannel(channelOptions, METRIC_CANDIDATES[key]);
      });
      return next;
    });
  }, [channelOptions]);

  useEffect(() => {
    carryRef.current = 0;
  }, [speed]);

  useEffect(() => {
    if (!playing || frames.length <= 1) return;

    const timer = window.setInterval(() => {
      setPlayhead((prev) => {
        carryRef.current += speed;
        const step = Math.floor(carryRef.current);
        if (step <= 0) return prev;
        carryRef.current -= step;
        const next = prev + step;
        if (next >= frames.length - 1) {
          return frames.length - 1;
        }
        return next;
      });
    }, 120);

    return () => {
      window.clearInterval(timer);
    };
  }, [playing, frames.length, speed]);

  useEffect(() => {
    if (!playing) return;
    if (!frames.length) {
      setPlaying(false);
      return;
    }
    if (playhead >= frames.length - 1) {
      setPlaying(false);
    }
  }, [playing, playhead, frames.length]);

  async function runAlignment() {
    if (!wellRunId) {
      message.warning(t("replay.chooseWellRun"));
      return;
    }

    const channelsPayload = METRIC_KEYS.flatMap((key) => {
      const picked = channelMap[key];
      if (!picked) return [];
      const decoded = decodeSourceChannel(picked);
      return [
        {
          alias: key,
          source: decoded.source || undefined,
          channel: decoded.channel,
          native_axis: "auto" as const,
          method: "nearest" as const
        }
      ];
    });

    if (!channelsPayload.length) {
      message.warning(t("replay.chooseChannels"));
      return;
    }

    setLoadingReplay(true);
    try {
      const result: WellRunAlignResponse = await alignWellRun(wellRunId, {
        axis: "time",
        grid_mode: "fixed",
        step_seconds: stepSeconds,
        max_rows: maxRows,
        segment_types: segmentTypes,
        channels: channelsPayload,
        axis_map: {
          enabled: true,
          max_gap_seconds: Math.max(90, stepSeconds * 8),
          max_gap_meters: 10,
          map_limit: 200000
        }
      });
      setRows(result.rows ?? []);
      setPlayhead(0);
      setPlaying((result.rows?.length ?? 0) > 1);
      message.success(t("replay.loadSuccess", { count: result.rows?.length ?? 0 }));
    } catch (err) {
      message.error(t("replay.loadFail"));
    } finally {
      setLoadingReplay(false);
    }
  }

  function autoMapChannels() {
    if (!channelOptions.length) return;
    setChannelMap((prev) => {
      const next: ChannelSelection = { ...prev };
      METRIC_KEYS.forEach((key) => {
        next[key] = pickDefaultChannel(channelOptions, METRIC_CANDIDATES[key]);
      });
      return next;
    });
    message.success(t("replay.autoMapped"));
  }

  function jumpToSegment(segmentId: string) {
    if (!frames.length) return;
    const target = segmentTimeline.find((segment) => segment.id === segmentId);
    if (!target) return;
    const targetIndex = frames.findIndex((frame) => dayjs(frame.ts).valueOf() >= target.start);
    if (targetIndex < 0) return;
    setPlaying(false);
    setPlayhead(targetIndex);
  }

  function toGaugePercent(key: MetricKey, value: number | null) {
    if (typeof value !== "number") return 0;
    const range = metricRanges[key];
    const span = Math.max(1e-6, range.max - range.min);
    return clamp(((value - range.min) / span) * 100, 0, 100);
  }

  const labels = {
    depthLabel: t("replay.depth"),
    azimuthLabel: metricLabel(t, "azimuth"),
    inclinationLabel: metricLabel(t, "inclination")
  };

  if (!tenantReady) {
    return <Alert type="warning" showIcon message={t("data.noTenant")} description={t("data.noTenantDesc")} />;
  }

  return (
    <PageShell>
      <PageHeader title={t("replay.title")} subtitle={t("replay.subtitle")} />

      <Card className="wv-toolbar-card">
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={7}>
            <Space direction="vertical" style={{ width: "100%" }} size={6}>
              <Typography.Text>{t("replay.warehouse")}</Typography.Text>
              <Select
                value={warehouseId ?? "all"}
                style={{ width: "100%" }}
                options={[
                  { value: "all", label: t("replay.allWarehouses") },
                  ...warehouses.map((warehouse) => ({
                    value: warehouse.id,
                    label: warehouse.name
                  }))
                ]}
                onChange={(value) => setWarehouseId(value === "all" ? null : value)}
              />
            </Space>
          </Col>

          <Col xs={24} lg={9}>
            <Space direction="vertical" style={{ width: "100%" }} size={6}>
              <Typography.Text>{t("replay.wellRun")}</Typography.Text>
              <Select
                value={wellRunId ?? undefined}
                style={{ width: "100%" }}
                options={wellRuns.map((run) => ({
                  value: run.id,
                  label: `${run.name}${run.well_name ? ` · ${run.well_name}` : ""}`
                }))}
                onChange={(value) => {
                  setWellRunId(value);
                  setRows([]);
                  setPlayhead(0);
                  setPlaying(false);
                }}
                placeholder={t("replay.chooseWellRun")}
              />
            </Space>
          </Col>

          <Col xs={12} lg={4}>
            <Space direction="vertical" style={{ width: "100%" }} size={6}>
              <Typography.Text>{t("replay.stepSeconds")}</Typography.Text>
              <InputNumber
                min={1}
                max={30}
                value={stepSeconds}
                onChange={(value) => setStepSeconds(Number(value || 1))}
                style={{ width: "100%" }}
              />
            </Space>
          </Col>

          <Col xs={12} lg={4}>
            <Space direction="vertical" style={{ width: "100%" }} size={6}>
              <Typography.Text>{t("replay.maxRows")}</Typography.Text>
              <InputNumber
                min={500}
                max={20000}
                step={500}
                value={maxRows}
                onChange={(value) => setMaxRows(Number(value || 2000))}
                style={{ width: "100%" }}
              />
            </Space>
          </Col>

          <Col xs={24}>
            <Space wrap size={8}>
              <Typography.Text>{t("replay.segmentFilter")}</Typography.Text>
              <Select
                mode="multiple"
                style={{ minWidth: 320 }}
                value={segmentTypes}
                options={availableSegmentTypes.map((item) => ({ value: item, label: item }))}
                onChange={(values) => setSegmentTypes(values)}
                placeholder={t("replay.segmentFilter")}
              />
              <Button onClick={autoMapChannels}>{t("replay.autoMap")}</Button>
              <Button type="primary" icon={<ReloadOutlined />} onClick={runAlignment} loading={loadingReplay}>
                {t("replay.loadData")}
              </Button>
            </Space>
          </Col>
        </Row>

        <div style={{ marginTop: 12 }}>
          <Row gutter={[12, 12]}>
            {METRIC_KEYS.map((key) => (
              <Col xs={24} sm={12} lg={8} xl={6} key={key}>
                <Space direction="vertical" style={{ width: "100%" }} size={4}>
                  <Typography.Text type="secondary">{metricLabel(t, key)}</Typography.Text>
                  <Select
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    value={channelMap[key] ?? undefined}
                    options={channelOptions}
                    onChange={(value) =>
                      setChannelMap((prev) => ({
                        ...prev,
                        [key]: value ?? null
                      }))
                    }
                  />
                </Space>
              </Col>
            ))}
          </Row>
        </div>

        <div style={{ marginTop: 12 }}>
          <Space wrap>
            <Tag color="blue">
              {t("replay.channelsMapped")}: {mappedCount}/{METRIC_KEYS.length}
            </Tag>
            <Tag color={frames.length ? "success" : "default"}>
              {t("replay.timeline")}: {frames.length}
            </Tag>
            <Tag color="geekblue">
              {t("replay.quality")}: {(dataCoverage * 100).toFixed(1)}%
            </Tag>
            {activeSegment ? <Tag color="purple">{t("replay.activeSegment")}: {activeSegment.type}</Tag> : null}
          </Space>
          <Space wrap style={{ marginTop: 10 }}>
            <Typography.Text type="secondary">{t("replay.jumpSegment")}</Typography.Text>
            <Select
              style={{ minWidth: 280 }}
              allowClear
              placeholder={t("replay.jumpSegment")}
              options={segmentTimeline.map((segment) => ({
                value: segment.id,
                label: `${segment.type} · ${dayjs(segment.start).format("MM-DD HH:mm:ss")}`
              }))}
              onChange={(value) => {
                if (value) jumpToSegment(value);
              }}
            />
          </Space>
        </div>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <Card
            title={t("replay.scene")}
            extra={
              <Space>
                <Button
                  icon={<StepBackwardOutlined />}
                  disabled={!frames.length}
                  onClick={() => {
                    setPlaying(false);
                    setPlayhead((prev) => Math.max(0, prev - 1));
                  }}
                >
                  {t("replay.stepPrev")}
                </Button>
                <Button
                  type="primary"
                  icon={playing ? <PauseOutlined /> : <CaretRightOutlined />}
                  disabled={!frames.length}
                  onClick={() => {
                    if (playing) {
                      setPlaying(false);
                    } else {
                      if (playhead >= frames.length - 1) {
                        setPlayhead(0);
                      }
                      carryRef.current = 0;
                      setPlaying(true);
                    }
                  }}
                >
                  {playing ? t("replay.pause") : t("replay.play")}
                </Button>
                <Button
                  icon={<StepForwardOutlined />}
                  disabled={!frames.length}
                  onClick={() => {
                    setPlaying(false);
                    setPlayhead((prev) => Math.min(Math.max(0, frames.length - 1), prev + 1));
                  }}
                >
                  {t("replay.stepNext")}
                </Button>
              </Space>
            }
          >
            {loadingMeta ? <Spin size="small" /> : null}

            {frames.length ? (
              <Space direction="vertical" style={{ width: "100%" }} size={14}>
                <DrillScene
                  frame={currentFrame}
                  depth={currentDepth}
                  depthRange={depthRange}
                  soilLayers={soilLayers}
                  playing={playing}
                  labels={labels}
                />

                <Row gutter={[12, 12]} align="middle">
                  <Col xs={24} md={6}>
                    <Space direction="vertical" style={{ width: "100%" }} size={4}>
                      <Typography.Text type="secondary">{t("replay.speed")}</Typography.Text>
                      <Select
                        value={speed}
                        options={[
                          { value: 0.5, label: "0.5x" },
                          { value: 1, label: "1x" },
                          { value: 2, label: "2x" },
                          { value: 4, label: "4x" },
                          { value: 8, label: "8x" }
                        ]}
                        onChange={(value) => {
                          setSpeed(value);
                          carryRef.current = 0;
                        }}
                      />
                    </Space>
                  </Col>
                  <Col xs={24} md={18}>
                    <Space direction="vertical" style={{ width: "100%" }} size={2}>
                      <Typography.Text type="secondary">
                        {formatTs(currentFrame?.ts)} · {t("replay.depth")}: {currentDepth.toFixed(1)} m
                      </Typography.Text>
                      <Slider
                        min={0}
                        max={Math.max(0, frames.length - 1)}
                        value={currentIndex}
                        onChange={(value) => {
                          setPlaying(false);
                          setPlayhead(value);
                        }}
                      />
                    </Space>
                  </Col>
                </Row>
              </Space>
            ) : (
              <Empty description={t("replay.noFrames")} />
            )}
          </Card>
        </Col>

        <Col xs={24} xl={8}>
          <Card title={t("replay.gauges")}>
            {frames.length && currentFrame ? (
              <Space direction="vertical" size={16} style={{ width: "100%" }}>
                <Row gutter={[10, 10]}>
                  {["pressure", "vibration", "wob", "rpm"].map((item) => {
                    const key = item as MetricKey;
                    const value = currentFrame.metrics[key];
                    return (
                      <Col span={12} key={key}>
                        <Card size="small" styles={{ body: { padding: 10 } }}>
                          <Typography.Text type="secondary">{metricLabel(t, key)}</Typography.Text>
                          <Progress
                            type="dashboard"
                            percent={toGaugePercent(key, value)}
                            strokeColor={METRIC_COLORS[key]}
                            format={() =>
                              typeof value === "number"
                                ? `${value.toFixed(1)} ${METRIC_UNITS[key]}`
                                : "--"
                            }
                            size={96}
                          />
                        </Card>
                      </Col>
                    );
                  })}
                </Row>

                <Card size="small" title={t("replay.direction")}>
                  <Row gutter={12} align="middle">
                    <Col span={12}>
                      <Statistic
                        title={metricLabel(t, "inclination")}
                        value={currentFrame.metrics.inclination ?? 0}
                        precision={1}
                        suffix="deg"
                      />
                    </Col>
                    <Col span={12}>
                      <Statistic
                        title={metricLabel(t, "azimuth")}
                        value={currentFrame.metrics.azimuth ?? 0}
                        precision={1}
                        suffix="deg"
                      />
                    </Col>
                  </Row>
                  <div
                    style={{
                      marginTop: 8,
                      width: 130,
                      height: 130,
                      borderRadius: "50%",
                      border: "2px solid #d9d9d9",
                      position: "relative",
                      marginInline: "auto",
                      background: "radial-gradient(circle at center, #ffffff 20%, #f0f5ff 100%)"
                    }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        left: "50%",
                        top: "50%",
                        width: 2,
                        height: 48,
                        background: "#1677ff",
                        transform: `translate(-50%, -100%) rotate(${currentFrame.metrics.azimuth ?? 0}deg)`,
                        transformOrigin: "50% 100%",
                        borderRadius: 4
                      }}
                    />
                    <div
                      style={{
                        position: "absolute",
                        left: "50%",
                        top: "50%",
                        width: 10,
                        height: 10,
                        borderRadius: "50%",
                        background: "#1677ff",
                        transform: "translate(-50%, -50%)"
                      }}
                    />
                  </div>
                </Card>

                <Card size="small" title={t("replay.soil")}>
                  <Space direction="vertical" style={{ width: "100%" }} size={6}>
                    {soilLayers.map((layer) => {
                      const active = currentDepth >= layer.top && currentDepth <= layer.bottom;
                      return (
                        <div
                          key={`${layer.name}-${layer.top}`}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            padding: "6px 8px",
                            borderRadius: 8,
                            background: active ? "rgba(22, 119, 255, 0.08)" : "transparent",
                            border: `1px solid ${active ? "#91caff" : "#f0f0f0"}`
                          }}
                        >
                          <Space>
                            <span
                              style={{
                                width: 12,
                                height: 12,
                                borderRadius: 2,
                                background: layer.color,
                                display: "inline-block"
                              }}
                            />
                            <Typography.Text>{layer.name}</Typography.Text>
                          </Space>
                          <Typography.Text type="secondary">
                            {layer.top.toFixed(0)}-{layer.bottom.toFixed(0)} m
                          </Typography.Text>
                        </div>
                      );
                    })}
                  </Space>
                </Card>
              </Space>
            ) : (
              <Empty description={t("replay.noFrames")} />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card title={t("replay.trend")}>
            {frames.length ? (
              <div style={{ height: 280 }}>
                <ResponsiveContainer>
                  <LineChart data={trendData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                    <XAxis
                      type="number"
                      dataKey="tms"
                      domain={["dataMin", "dataMax"]}
                      tickFormatter={(value) => dayjs(Number(value)).format("HH:mm:ss")}
                      minTickGap={24}
                    />
                    <YAxis yAxisId="left" />
                    <YAxis yAxisId="right" orientation="right" />
                    <Tooltip labelFormatter={(value) => formatTs(dayjs(Number(value)).toISOString())} />
                    {trendSegments.map((segment) => (
                      <ReferenceArea
                        key={segment.id}
                        x1={segment.x1}
                        x2={segment.x2}
                        yAxisId="left"
                        fill={segment.color}
                        fillOpacity={0.1}
                        strokeOpacity={0}
                      />
                    ))}
                    <Line yAxisId="left" type="monotone" dataKey="pressure" stroke={METRIC_COLORS.pressure} dot={false} connectNulls />
                    <Line yAxisId="left" type="monotone" dataKey="wob" stroke={METRIC_COLORS.wob} dot={false} connectNulls />
                    <Line yAxisId="right" type="monotone" dataKey="rpm" stroke={METRIC_COLORS.rpm} dot={false} connectNulls />
                    <Line yAxisId="right" type="monotone" dataKey="vibration" stroke={METRIC_COLORS.vibration} dot={false} connectNulls />
                    <ReferenceLine
                      x={currentFrame?.ts ? dayjs(currentFrame.ts).valueOf() : undefined}
                      yAxisId="left"
                      stroke="#595959"
                      strokeDasharray="4 4"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <Empty description={t("replay.noFrames")} />
            )}
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card title={t("replay.trajectory")}>
            {trajectoryWindowData.length ? (
              <Space direction="vertical" size={10} style={{ width: "100%" }}>
                <div style={{ height: 230 }}>
                  <ResponsiveContainer>
                    <LineChart data={trajectoryWindowData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                      <XAxis
                        type="number"
                        dataKey="x"
                        domain={["dataMin", "dataMax"]}
                        tickFormatter={(value) => `${Number(value).toFixed(1)} m`}
                      />
                      <YAxis
                        type="number"
                        dataKey="y"
                        domain={["dataMin", "dataMax"]}
                        tickFormatter={(value) => `${Number(value).toFixed(1)} m`}
                      />
                      <Tooltip
                        formatter={(value: number, name: string) => [`${Number(value).toFixed(2)} m`, name === "y" ? "N-S" : "E-W"]}
                        labelFormatter={(_, payload) => {
                          const point = payload?.[0]?.payload as { ts?: string } | undefined;
                          return point?.ts ? formatTs(point.ts) : "-";
                        }}
                      />
                      <Line type="monotone" dataKey="y" stroke="#1677ff" strokeWidth={2} dot={false} isAnimationActive={false} />
                      {currentTrajectoryPoint ? (
                        <ReferenceDot
                          x={currentTrajectoryPoint.x}
                          y={currentTrajectoryPoint.y}
                          r={5}
                          fill="#f5222d"
                          stroke="#ffffff"
                        />
                      ) : null}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <Row gutter={12}>
                  <Col span={12}>
                    <Statistic
                      title={t("replay.displacementEw")}
                      value={currentTrajectoryPoint?.x ?? 0}
                      precision={2}
                      suffix="m"
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title={t("replay.displacementNs")}
                      value={currentTrajectoryPoint?.y ?? 0}
                      precision={2}
                      suffix="m"
                    />
                  </Col>
                </Row>
              </Space>
            ) : (
              <Empty description={t("replay.noFrames")} />
            )}
          </Card>
        </Col>
      </Row>
    </PageShell>
  );
}
