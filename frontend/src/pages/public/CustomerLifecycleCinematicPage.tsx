import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Play, Pause, RotateCcw, Maximize2, ArrowLeft } from 'lucide-react';

interface StageDef {
  id: string;
  label: string;
  num: string;
  meta: string;
  color: string;
  glow: string;
  val: string;
}

const STAGES: StageDef[] = [
  {
    id: 'NEW',
    label: 'NEW',
    num: '01',
    meta: 'Acquisition & Genesis',
    color: '#38BDF8',
    glow: 'rgba(56, 189, 248, 0.85)',
    val: '1.0x',
  },
  {
    id: 'ACTIVE',
    label: 'ACTIVE',
    num: '02',
    meta: 'Engagement & Value Realization',
    color: '#8B5CF6',
    glow: 'rgba(139, 92, 246, 0.9)',
    val: '2.4x',
  },
  {
    id: 'SUBSCRIBED',
    label: 'SUBSCRIBED',
    num: '03',
    meta: 'Recurring Revenue Anchor',
    color: '#E83E8C',
    glow: 'rgba(232, 62, 140, 0.95)',
    val: '5.8x',
  },
  {
    id: 'RENEWING',
    label: 'RENEWING',
    num: '04',
    meta: 'Compounding Trust & Retention',
    color: '#10B981',
    glow: 'rgba(16, 185, 129, 0.95)',
    val: '12.0x',
  },
  {
    id: 'GROWING',
    label: 'GROWING',
    num: '05',
    meta: 'Ecosystem Expansion & Multi-Seat Scale',
    color: '#34D399',
    glow: 'rgba(52, 211, 153, 1.0)',
    val: '25.0x',
  },
];

export function CustomerLifecycleCinematicPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const [isPlaying, setIsPlaying] = useState(true);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);
  const [currentStage, setCurrentStage] = useState<StageDef>(STAGES[0]);
  const [timeFormatted, setTimeFormatted] = useState('00:00.00 / 00:10.00');
  const [progressPct, setProgressPct] = useState(0);

  // Use refs for animation loop variables to avoid closures lag
  const animState = useRef({
    currentTime: 0.0,
    isPlaying: true,
    speed: 1.0,
    lastTime: performance.now(),
    trail: [] as Array<{ x: number; y: number; color: string; radius: number }>,
    wavefronts: [] as Array<{ x: number; y: number; r: number; maxR: number; color: string; alpha: number; growth: number }>,
    lastStageId: '',
  });

  useEffect(() => {
    animState.current.isPlaying = isPlaying;
  }, [isPlaying]);

  useEffect(() => {
    animState.current.speed = playbackSpeed;
  }, [playbackSpeed]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) return;

    // 4K Cinema buffer
    const WIDTH = 3840;
    const HEIGHT = 2160;
    canvas.width = WIDTH;
    canvas.height = HEIGHT;

    const DURATION = 10.0;
    const CENTER_X = WIDTH * 0.5;
    const CENTER_Y = HEIGHT * 0.5;
    const RADIUS_X = WIDTH * 0.28;
    const RADIUS_Y = HEIGHT * 0.32;
    const TILT_ANGLE = -0.15;
    const START_ANGLE = 3.4;
    const TOTAL_TRAVEL_RADIANS = Math.PI * 2.15;

    function getOrbitPoint(angleRad: number, rx = RADIUS_X, ry = RADIUS_Y, cx = CENTER_X, cy = CENTER_Y, tilt = TILT_ANGLE) {
      const cosA = Math.cos(angleRad);
      const sinA = Math.sin(angleRad);
      const unrotatedX = rx * cosA;
      const unrotatedY = ry * sinA;
      const rotX = unrotatedX * Math.cos(tilt) - unrotatedY * Math.sin(tilt);
      const rotY = unrotatedX * Math.sin(tilt) + unrotatedY * Math.cos(tilt);
      return { x: cx + rotX, y: cy + rotY };
    }

    // Cosmic background particles
    const bgParticles = Array.from({ length: 220 }, (_, i) => ({
      x: Math.random() * WIDTH,
      y: Math.random() * HEIGHT,
      r: Math.random() * 2.2 + 0.6,
      alpha: Math.random() * 0.5 + 0.15,
      phase: Math.random() * Math.PI * 2,
      color: i % 3 === 0 ? '#3F51C9' : i % 3 === 1 ? '#6C2BD9' : '#00E5FF',
    }));

    // Secondary interconnected customer journeys
    const secondaryJourneys = Array.from({ length: 14 }, (_, j) => {
      const scale = 0.55 + j * 0.08;
      const tiltOffset = -0.3 + j * 0.08;
      const speed = 0.4 + (j % 4) * 0.22;
      const phaseOffset = j * 0.85;
      const baseColor = j % 4 === 0 ? '#38BDF8' : j % 4 === 1 ? '#8B5CF6' : j % 4 === 2 ? '#E83E8C' : '#10B981';
      return {
        rx: RADIUS_X * scale,
        ry: RADIUS_Y * scale * 0.88,
        tilt: tiltOffset,
        cx: CENTER_X + Math.sin(j * 1.3) * WIDTH * 0.08,
        cy: CENTER_Y + Math.cos(j * 1.1) * HEIGHT * 0.06,
        speed,
        phaseOffset,
        baseColor,
        nodeRadius: 8 + (j % 5) * 4,
      };
    });

    function hexToRgb(hex: string) {
      const clean = hex.replace('#', '');
      const bigint = parseInt(clean, 16);
      return { r: (bigint >> 16) & 255, g: (bigint >> 8) & 255, b: bigint & 255 };
    }

    function lerpColor(hexA: string, hexB: string, amt: number) {
      const a = hexToRgb(hexA);
      const b = hexToRgb(hexB);
      const r = Math.round(a.r + (b.r - a.r) * amt);
      const g = Math.round(a.g + (b.g - a.g) * amt);
      const bl = Math.round(a.b + (b.b - a.b) * amt);
      return `rgb(${r}, ${g}, ${bl})`;
    }

    function getHeroNode(t: number) {
      let currentPos = { x: 0, y: 0 };
      let nodeColor = '#38BDF8';
      let nodeRadius = 24;
      let auraIntensity = 1.0;
      let stageIdx = 0;

      if (t < 1.8) {
        const progress = t / 1.8;
        const ease = 1 - Math.pow(1 - progress, 3);
        const startX = WIDTH * 0.08;
        const startY = HEIGHT * 0.15;
        const orbitStart = getOrbitPoint(START_ANGLE);
        currentPos.x = startX + (orbitStart.x - startX) * ease;
        currentPos.y = startY + (orbitStart.y - startY) * ease;
        nodeColor = lerpColor('#38BDF8', '#3F51C9', progress);
        nodeRadius = 22 + progress * 6;
        stageIdx = 0;
      } else {
        const orbitProgress = (t - 1.8) / (DURATION - 1.8);
        const angle = START_ANGLE + orbitProgress * TOTAL_TRAVEL_RADIANS;
        currentPos = getOrbitPoint(angle);

        if (t < 4.0) {
          stageIdx = 1;
          const p = (t - 1.8) / (4.0 - 1.8);
          nodeColor = lerpColor('#3F51C9', '#8B5CF6', p);
          nodeRadius = 28 + p * 8;
          auraIntensity = 1.2;
        } else if (t < 6.2) {
          stageIdx = 2;
          const p = (t - 4.0) / (6.2 - 4.0);
          nodeColor = lerpColor('#8B5CF6', '#E83E8C', p);
          nodeRadius = 36 + p * 10;
          auraIntensity = 1.5;
        } else if (t < 8.2) {
          stageIdx = 3;
          const p = (t - 6.2) / (8.2 - 6.2);
          nodeColor = lerpColor('#E83E8C', '#10B981', p);
          nodeRadius = 46 + p * 12;
          auraIntensity = 1.8;
        } else {
          stageIdx = 4;
          const p = (t - 8.2) / (10.0 - 8.2);
          nodeColor = lerpColor('#10B981', '#34D399', p);
          nodeRadius = 58 + Math.sin(t * 8) * 4;
          auraIntensity = 2.4;
        }
      }

      return {
        pos: currentPos,
        color: nodeColor,
        radius: nodeRadius,
        aura: auraIntensity,
        stage: STAGES[stageIdx],
      };
    }

    function getCamera(t: number) {
      let zoom = 1.0;
      let panX = 0;
      let panY = 0;

      if (t < 2.0) {
        const p = t / 2.0;
        zoom = 1.5 - p * 0.2;
        panX = (1 - p) * (WIDTH * 0.18);
        panY = (1 - p) * (HEIGHT * 0.12);
      } else if (t < 6.0) {
        const p = (t - 2.0) / 4.0;
        zoom = 1.3 - p * 0.2;
        panX = Math.sin(t * 0.8) * 30;
        panY = Math.cos(t * 0.8) * 20;
      } else if (t < 8.2) {
        const p = (t - 6.0) / 2.2;
        zoom = 1.1 - p * 0.12;
        panX = Math.sin(t * 0.6) * 20;
        panY = Math.cos(t * 0.6) * 15;
      } else {
        const p = (t - 8.2) / 1.8;
        zoom = 0.98 - p * 0.08;
        panX = 0;
        panY = 0;
      }

      return { zoom, panX, panY };
    }

    let animationFrameId: number;

    const render = (now: number) => {
      const state = animState.current;
      const delta = (now - state.lastTime) / 1000;
      state.lastTime = now;

      if (state.isPlaying) {
        state.currentTime += delta * state.speed;
        if (state.currentTime >= DURATION) {
          state.currentTime = 0.0;
          state.trail.length = 0;
          state.wavefronts.length = 0;
        }
      }

      const t = state.currentTime;
      const hero = getHeroNode(t);
      const camera = getCamera(t);

      // Trigger state update for React HUD at throttled interval
      if (hero.stage.id !== state.lastStageId) {
        state.lastStageId = hero.stage.id;
        setCurrentStage(hero.stage);
        state.wavefronts.push({
          x: hero.pos.x,
          y: hero.pos.y,
          r: 10,
          maxR: 450,
          color: hero.color,
          alpha: 1.0,
          growth: 12,
        });
      }

      // Trail
      state.trail.unshift({
        x: hero.pos.x,
        y: hero.pos.y,
        color: hero.color,
        radius: hero.radius * 0.45,
      });
      if (state.trail.length > 180) state.trail.pop();

      // Clear & Background
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, WIDTH, HEIGHT);

      const bgGrad = ctx.createRadialGradient(CENTER_X, CENTER_Y, 200, CENTER_X, CENTER_Y, WIDTH * 0.85);
      bgGrad.addColorStop(0, '#090F2C');
      bgGrad.addColorStop(0.35, '#060B20');
      bgGrad.addColorStop(0.7, '#040714');
      bgGrad.addColorStop(1, '#020308');
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, WIDTH, HEIGHT);

      // Nebula Shaders
      ctx.globalCompositeOperation = 'screen';
      const neb1 = ctx.createRadialGradient(WIDTH * 0.35, HEIGHT * 0.4, 80, WIDTH * 0.35, HEIGHT * 0.4, 1100);
      neb1.addColorStop(0, 'rgba(108, 43, 217, 0.18)');
      neb1.addColorStop(0.6, 'rgba(63, 81, 201, 0.08)');
      neb1.addColorStop(1, 'transparent');
      ctx.fillStyle = neb1;
      ctx.fillRect(0, 0, WIDTH, HEIGHT);

      const neb2 = ctx.createRadialGradient(WIDTH * 0.68, HEIGHT * 0.55, 100, WIDTH * 0.68, HEIGHT * 0.55, 1200);
      neb2.addColorStop(0, 'rgba(232, 62, 140, 0.14)');
      neb2.addColorStop(0.5, 'rgba(16, 185, 129, 0.08)');
      neb2.addColorStop(1, 'transparent');
      ctx.fillStyle = neb2;
      ctx.fillRect(0, 0, WIDTH, HEIGHT);

      // Cosmic background particles
      ctx.globalCompositeOperation = 'lighter';
      for (let i = 0; i < bgParticles.length; i++) {
        const p = bgParticles[i];
        const pulse = Math.sin(t * 2 + p.phase);
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = p.alpha * (0.6 + 0.4 * pulse);
        ctx.fill();
      }
      ctx.globalAlpha = 1.0;

      // Apply Macro Camera Transform
      ctx.save();
      ctx.translate(CENTER_X, CENTER_Y);
      ctx.scale(camera.zoom, camera.zoom);
      ctx.translate(-CENTER_X + camera.panX, -CENTER_Y + camera.panY);

      // Wavefronts
      for (let w = state.wavefronts.length - 1; w >= 0; w--) {
        const wave = state.wavefronts[w];
        wave.r += wave.growth;
        wave.alpha = Math.max(0, 1.0 - wave.r / wave.maxR);
        if (wave.alpha <= 0) {
          state.wavefronts.splice(w, 1);
          continue;
        }
        ctx.beginPath();
        ctx.arc(wave.x, wave.y, wave.r, 0, Math.PI * 2);
        ctx.strokeStyle = wave.color;
        ctx.lineWidth = 4 * wave.alpha;
        ctx.globalAlpha = wave.alpha * 0.65;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(wave.x, wave.y, wave.r * 0.75, 0, Math.PI * 2);
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 1.5 * wave.alpha;
        ctx.globalAlpha = wave.alpha * 0.4;
        ctx.stroke();
      }
      ctx.globalAlpha = 1.0;

      // Interconnected ecosystem journeys
      const ecosystemIntensity = Math.min(1.0, Math.max(0.0, (t - 3.5) / 5.5));
      if (ecosystemIntensity > 0.01) {
        ctx.globalCompositeOperation = 'lighter';
        for (let j = 0; j < secondaryJourneys.length; j++) {
          const sj = secondaryJourneys[j];
          ctx.beginPath();
          const steps = 60;
          for (let s = 0; s <= steps; s++) {
            const ang = (s / steps) * Math.PI * 2;
            const pt = getOrbitPoint(ang, sj.rx, sj.ry, sj.cx, sj.cy, sj.tilt);
            if (s === 0) ctx.moveTo(pt.x, pt.y);
            else ctx.lineTo(pt.x, pt.y);
          }
          ctx.closePath();
          ctx.strokeStyle = sj.baseColor;
          ctx.lineWidth = 2.0 * ecosystemIntensity;
          ctx.globalAlpha = 0.18 * ecosystemIntensity;
          ctx.stroke();

          const nodeAng = t * sj.speed + sj.phaseOffset;
          const nodePt = getOrbitPoint(nodeAng, sj.rx, sj.ry, sj.cx, sj.cy, sj.tilt);

          const secGlow = ctx.createRadialGradient(nodePt.x, nodePt.y, 2, nodePt.x, nodePt.y, sj.nodeRadius * 4.5);
          secGlow.addColorStop(0, '#FFFFFF');
          secGlow.addColorStop(0.3, sj.baseColor);
          secGlow.addColorStop(1, 'transparent');
          ctx.fillStyle = secGlow;
          ctx.globalAlpha = 0.75 * ecosystemIntensity;
          ctx.beginPath();
          ctx.arc(nodePt.x, nodePt.y, sj.nodeRadius * 4.5, 0, Math.PI * 2);
          ctx.fill();

          ctx.fillStyle = '#FFFFFF';
          ctx.globalAlpha = 0.9 * ecosystemIntensity;
          ctx.beginPath();
          ctx.arc(nodePt.x, nodePt.y, sj.nodeRadius * 0.8, 0, Math.PI * 2);
          ctx.fill();

          const dist = Math.hypot(hero.pos.x - nodePt.x, hero.pos.y - nodePt.y);
          if (dist < 850 && ecosystemIntensity > 0.4) {
            ctx.beginPath();
            ctx.moveTo(hero.pos.x, hero.pos.y);
            ctx.lineTo(nodePt.x, nodePt.y);
            ctx.strokeStyle = sj.baseColor;
            ctx.lineWidth = 1.8;
            ctx.globalAlpha = (1 - dist / 850) * 0.45 * ecosystemIntensity;
            ctx.stroke();
          }
        }
        ctx.globalAlpha = 1.0;
      }

      // Master Lifecycle Orbital Curve
      ctx.globalCompositeOperation = 'lighter';
      ctx.beginPath();
      const mainSteps = 120;
      for (let m = 0; m <= mainSteps; m++) {
        const ang = (m / mainSteps) * Math.PI * 2;
        const pt = getOrbitPoint(ang);
        if (m === 0) ctx.moveTo(pt.x, pt.y);
        else ctx.lineTo(pt.x, pt.y);
      }
      ctx.closePath();
      ctx.strokeStyle = 'rgba(63, 81, 201, 0.25)';
      ctx.lineWidth = 3.0;
      ctx.stroke();

      // Lit Curve
      const travelProgress = Math.min(1.0, Math.max(0.0, (t - 1.8) / (DURATION - 1.8)));
      if (travelProgress > 0) {
        ctx.beginPath();
        const litSteps = Math.floor(mainSteps * travelProgress);
        for (let l = 0; l <= litSteps; l++) {
          const ang = START_ANGLE + (l / mainSteps) * TOTAL_TRAVEL_RADIANS;
          const pt = getOrbitPoint(ang);
          if (l === 0) ctx.moveTo(pt.x, pt.y);
          else ctx.lineTo(pt.x, pt.y);
        }
        const activeGrad = ctx.createLinearGradient(WIDTH * 0.2, HEIGHT * 0.2, WIDTH * 0.8, HEIGHT * 0.8);
        activeGrad.addColorStop(0, '#38BDF8');
        activeGrad.addColorStop(0.35, '#8B5CF6');
        activeGrad.addColorStop(0.7, '#E83E8C');
        activeGrad.addColorStop(1, '#10B981');
        ctx.strokeStyle = activeGrad;
        ctx.lineWidth = 6.0;
        ctx.shadowColor = hero.color;
        ctx.shadowBlur = 25;
        ctx.stroke();
        ctx.shadowBlur = 0;
      }

      // Entrance Bezier
      if (t < 2.5) {
        const entAlpha = Math.max(0, 1.0 - t / 2.5);
        const startX = WIDTH * 0.08;
        const startY = HEIGHT * 0.15;
        const orbitStart = getOrbitPoint(START_ANGLE);
        ctx.beginPath();
        ctx.moveTo(startX, startY);
        ctx.quadraticCurveTo(WIDTH * 0.15, HEIGHT * 0.45, orbitStart.x, orbitStart.y);
        ctx.strokeStyle = '#38BDF8';
        ctx.lineWidth = 4.0;
        ctx.globalAlpha = entAlpha * 0.6;
        ctx.stroke();
        ctx.globalAlpha = 1.0;
      }

      // Stage Milestones
      const milestoneAngles = [
        { name: 'NEW', ang: START_ANGLE, color: '#38BDF8' },
        { name: 'ACTIVE', ang: START_ANGLE + 0.28 * TOTAL_TRAVEL_RADIANS, color: '#8B5CF6' },
        { name: 'SUBSCRIBED', ang: START_ANGLE + 0.55 * TOTAL_TRAVEL_RADIANS, color: '#E83E8C' },
        { name: 'RENEWING', ang: START_ANGLE + 0.78 * TOTAL_TRAVEL_RADIANS, color: '#10B981' },
        { name: 'GROWING', ang: START_ANGLE + 0.98 * TOTAL_TRAVEL_RADIANS, color: '#34D399' },
      ];

      for (let k = 0; k < milestoneAngles.length; k++) {
        const ms = milestoneAngles[k];
        const pt = getOrbitPoint(ms.ang);
        const isPassed = travelProgress >= k / (milestoneAngles.length - 1);

        ctx.beginPath();
        ctx.arc(pt.x, pt.y, isPassed ? 16 : 10, 0, Math.PI * 2);
        ctx.strokeStyle = ms.color;
        ctx.lineWidth = isPassed ? 2.5 : 1.5;
        ctx.globalAlpha = isPassed ? 0.85 : 0.35;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(pt.x, pt.y, isPassed ? 7 : 4, 0, Math.PI * 2);
        ctx.fillStyle = isPassed ? ms.color : 'rgba(255,255,255,0.4)';
        ctx.globalAlpha = isPassed ? 0.95 : 0.4;
        ctx.fill();

        ctx.font = '600 24px "Plus Jakarta Sans", sans-serif';
        ctx.fillStyle = isPassed ? '#FFFFFF' : 'rgba(255, 255, 255, 0.45)';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        const labelDist = 58;
        const angleToCenter = Math.atan2(pt.y - CENTER_Y, pt.x - CENTER_X);
        const labelX = pt.x + Math.cos(angleToCenter) * labelDist;
        const labelY = pt.y + Math.sin(angleToCenter) * labelDist;
        ctx.fillText(ms.name, labelX, labelY);
      }
      ctx.globalAlpha = 1.0;

      // Particle Trail
      for (let i = 0; i < state.trail.length - 1; i++) {
        const p1 = state.trail[i];
        const p2 = state.trail[i + 1];
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.strokeStyle = p1.color;
        ctx.lineWidth = p1.radius * (1 - i / state.trail.length);
        ctx.globalAlpha = (1 - i / state.trail.length) * 0.85;
        ctx.stroke();
      }
      ctx.globalAlpha = 1.0;

      // Hero Node
      const hx = hero.pos.x;
      const hy = hero.pos.y;
      const hr = hero.radius;

      // Anamorphic Lens Flare
      const flareWidth = hr * 14 * hero.aura;
      const flareHeight = hr * 1.6;
      const flareGrad = ctx.createRadialGradient(hx, hy, 2, hx, hy, flareWidth * 0.5);
      flareGrad.addColorStop(0, '#FFFFFF');
      flareGrad.addColorStop(0.15, hero.color);
      flareGrad.addColorStop(0.5, 'rgba(255, 255, 255, 0.15)');
      flareGrad.addColorStop(1, 'transparent');

      ctx.save();
      ctx.translate(hx, hy);
      ctx.scale(1, flareHeight / flareWidth);
      ctx.beginPath();
      ctx.arc(0, 0, flareWidth * 0.5, 0, Math.PI * 2);
      ctx.fillStyle = flareGrad;
      ctx.globalAlpha = 0.9;
      ctx.fill();
      ctx.restore();

      // Bloom
      const bloomGrad = ctx.createRadialGradient(hx, hy, hr * 0.2, hx, hy, hr * 5.2);
      bloomGrad.addColorStop(0, '#FFFFFF');
      bloomGrad.addColorStop(0.2, hero.color);
      bloomGrad.addColorStop(0.5, hero.color);
      bloomGrad.addColorStop(0.8, 'rgba(0,0,0,0)');
      bloomGrad.addColorStop(1, 'transparent');
      ctx.beginPath();
      ctx.arc(hx, hy, hr * 5.2, 0, Math.PI * 2);
      ctx.fillStyle = bloomGrad;
      ctx.globalAlpha = 0.65 * hero.aura;
      ctx.fill();

      // Glass Sphere
      const glassGrad = ctx.createRadialGradient(hx - hr * 0.35, hy - hr * 0.35, hr * 0.1, hx, hy, hr);
      glassGrad.addColorStop(0, '#FFFFFF');
      glassGrad.addColorStop(0.3, '#FFFFFF');
      glassGrad.addColorStop(0.7, hero.color);
      glassGrad.addColorStop(1, 'rgba(10, 15, 40, 0.8)');
      ctx.beginPath();
      ctx.arc(hx, hy, hr, 0, Math.PI * 2);
      ctx.fillStyle = glassGrad;
      ctx.globalAlpha = 1.0;
      ctx.fill();

      // Specular Arc
      ctx.beginPath();
      ctx.arc(hx, hy, hr * 0.9, -Math.PI * 0.75, -Math.PI * 0.1);
      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = 3.5;
      ctx.stroke();

      // Satellites
      for (let s = 0; s < 3; s++) {
        const satAngle = t * 4.5 + s * ((Math.PI * 2) / 3);
        const satDist = hr * 1.55;
        const sx = hx + Math.cos(satAngle) * satDist;
        const sy = hy + Math.sin(satAngle) * satDist * 0.65;
        ctx.beginPath();
        ctx.arc(sx, sy, 4.5, 0, Math.PI * 2);
        ctx.fillStyle = '#FFFFFF';
        ctx.shadowColor = hero.color;
        ctx.shadowBlur = 15;
        ctx.fill();
        ctx.shadowBlur = 0;
      }

      ctx.restore();
      ctx.restore();

      // Sync Time & Progress HUD
      const secs = Math.floor(t);
      const centis = Math.floor((t % 1) * 100);
      setTimeFormatted(`00:${secs.toString().padStart(2, '0')}.${centis.toString().padStart(2, '0')} / 00:10.00`);
      setProgressPct((t / DURATION) * 100);

      animationFrameId = requestAnimationFrame(render);
    };

    animationFrameId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  const handleScrub = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    animState.current.currentTime = ratio * 10.0;
    animState.current.trail.length = 0;
    animState.current.wavefronts.length = 0;
  };

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen().catch(console.error);
    } else {
      document.exitFullscreen();
    }
  };

  const handleRestart = () => {
    animState.current.currentTime = 0;
    animState.current.trail.length = 0;
    animState.current.wavefronts.length = 0;
    if (!isPlaying) setIsPlaying(true);
  };

  return (
    <div className="min-h-screen w-full bg-[#040714] text-slate-100 flex items-center justify-center p-0 md:p-6 select-none">
      <div
        ref={containerRef}
        className="relative w-full max-w-[177.78vh] aspect-video max-h-screen bg-[#040714] overflow-hidden shadow-2xl shadow-blue-950/40 md:rounded-2xl border border-slate-800/60"
      >
        <canvas ref={canvasRef} className="absolute inset-0 w-full h-full block" />

        {/* Ambient Film Overlays */}
        <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_center,transparent_40%,rgba(4,7,20,0.6)_80%,rgba(4,7,20,0.95)_100%)] mix-blend-multiply" />
        <div className="absolute inset-0 pointer-events-none bg-gradient-to-b from-blue-600/[0.03] via-transparent to-pink-600/[0.03]" />

        {/* Top Header */}
        <div className="absolute top-4 left-6 md:top-8 md:left-10 z-20 flex items-center gap-4">
          <Link
            to="/customer-lifecycle"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-900/60 hover:bg-slate-800/80 backdrop-blur-md border border-white/10 text-xs font-medium text-slate-300 transition"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Dashboard</span>
          </Link>

          <div className="flex items-center gap-2.5 px-3.5 py-1.5 rounded-full bg-slate-950/60 backdrop-blur-md border border-white/10">
            <span className="w-2 h-2 rounded-full bg-[#E83E8C] shadow-[0_0_8px_#E83E8C]" />
            <span className="text-xs font-bold tracking-[0.25em] uppercase text-white/90">Rooman Billing</span>
          </div>
          <span className="hidden sm:inline text-[11px] font-medium tracking-[0.2em] uppercase text-slate-400">
            Customer Lifecycle · 10s Cinematic
          </span>
        </div>

        {/* Top Right Specs */}
        <div className="absolute top-4 right-6 md:top-8 md:right-10 z-20 flex items-center gap-3">
          <div className="px-2.5 py-1 rounded bg-white/5 border border-white/10 text-[10px] font-bold tracking-widest text-white/70 uppercase">
            4K · 60 FPS UHD
          </div>
          <div className="font-mono text-xs tracking-wider text-slate-300">{timeFormatted}</div>
        </div>

        {/* Dynamic Stage Indicator */}
        <div className="absolute bottom-16 left-6 md:bottom-20 md:left-10 z-20 flex flex-col gap-1 pointer-events-none">
          <div className="flex items-center gap-2 text-xs font-bold tracking-[0.25em] uppercase" style={{ color: currentStage.color }}>
            <span className="px-1.5 py-0.5 rounded border text-[10px]" style={{ borderColor: currentStage.color }}>
              {currentStage.num}
            </span>
            <span>PHASE {currentStage.num} · VALUE {currentStage.val}</span>
          </div>
          <div className="text-2xl md:text-4xl font-extrabold uppercase tracking-wide text-white drop-shadow-[0_0_25px_rgba(255,255,255,0.4)]">
            {currentStage.label}
          </div>
          <div className="text-xs md:text-sm font-medium tracking-[0.15em] uppercase text-slate-400">
            {currentStage.meta}
          </div>
        </div>

        {/* Interactive Timeline & Control Dock */}
        <div className="absolute bottom-0 left-0 w-full p-4 md:p-6 bg-gradient-to-t from-[#040714]/90 via-[#040714]/50 to-transparent z-30 flex flex-col gap-3 opacity-90 hover:opacity-100 transition-opacity">
          {/* Scrubber Bar */}
          <div
            onClick={handleScrub}
            className="relative w-full h-1.5 bg-white/10 rounded-full cursor-pointer hover:h-2 transition-all"
          >
            <div
              className="absolute top-0 left-0 h-full rounded-full bg-gradient-to-r from-[#3F51C9] via-[#8B5CF6] via-[#E83E8C] to-[#10B981] shadow-[0_0_12px_rgba(16,185,129,0.6)]"
              style={{ width: `${progressPct}%` }}
            />
            {/* Stage Markers */}
            <div className="absolute inset-0 flex justify-between pointer-events-none">
              <span className="w-1.5 h-1.5 rounded-full bg-white/30" style={{ left: '0%' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-white/30" style={{ left: '20%' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-white/30" style={{ left: '40%' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-white/30" style={{ left: '62%' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-white/30" style={{ left: '82%' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-white/30" style={{ left: '100%' }} />
            </div>
          </div>

          {/* Buttons Row */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-white/10 hover:bg-white/20 border border-white/10 text-xs font-medium text-white transition"
              >
                {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                <span>{isPlaying ? 'Pause' : 'Play'}</span>
              </button>

              <button
                onClick={handleRestart}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-white/10 hover:bg-white/20 border border-white/10 text-xs font-medium text-white transition"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Replay</span>
              </button>
            </div>

            <div className="flex items-center gap-2">
              {[0.5, 1.0, 1.5].map((speed) => (
                <button
                  key={speed}
                  onClick={() => setPlaybackSpeed(speed)}
                  className={`px-2.5 py-1 rounded text-xs font-medium border transition ${
                    playbackSpeed === speed
                      ? 'bg-sky-500/20 border-sky-400 text-sky-300'
                      : 'bg-white/5 border-white/10 text-slate-300 hover:bg-white/10'
                  }`}
                >
                  {speed}x
                </button>
              ))}

              <button
                onClick={toggleFullscreen}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-white/10 hover:bg-white/20 border border-white/10 text-xs font-medium text-white transition"
              >
                <Maximize2 className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Fullscreen</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CustomerLifecycleCinematicPage;
