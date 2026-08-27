<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";

// 雷达扫描画布 Canvas 2D 逐帧绘制：同心圆网格 + 旋转扫掠扇形 + 光点（被扫过后渐隐）

const canvasRef = ref<HTMLCanvasElement | null>(null);

let ctx: CanvasRenderingContext2D | null = null;
let rafId = 0;
let resizeObserver: ResizeObserver | null = null;
// 扫掠前沿初始角度：设为一个已扫过一段的值（> TAIL_LENGTH），
// 让首帧尾巴就已罩住一段网格，避免从 0 起步导致"一亮一暗、过会才稳定"
let sweepAngle = Math.PI * 0.6; // 扫掠前沿当前角度（弧度）
let lastFrameTime = 0; // 上一帧时间戳，用于算帧间隔

/**
 * 扫掠角度取模到单圈 [0, 2π)。
 * 网格段 diff 用 (sweepAngle - a0 + 2π) % 2π 计算"已扫过角度"，
 * 跨 0/2π 边界时尾巴自然连续，且每圈都能重新扫到网格。
 */
const SWEEP_PERIOD = Math.PI * 2;

/** 扫掠速度：弧度/秒（Math.PI / 3 → 6 秒转一圈） */
const SWEEP_SPEED = Math.PI / 3;
/** 扫掠尾巴长度（弧度），尾巴内透明度线性衰减 */
const TAIL_LENGTH = Math.PI / 2.5;
/** 光点被扫过后的余晖范围（按角度计） */
const BLIP_FADE = Math.PI * 0.5;

// Canvas 里直接写 rgba 最稳妥：
const COLOR_SWEEP = "160, 120, 250"; // 扫掠
const COLOR_BLIP_BLUE = "99, 102, 241"; // 青亮蓝
const COLOR_BLIP_ORANGE = "255, 170, 90"; // 暖橙——和蓝底形成互补对比，最跳
const COLOR_BLIP_CYAN = "56, 224, 235"; // 青绿
const COLOR_BLIP_PINK = "244, 114, 182"; // 粉红
const COLOR_BLIP_YELLOW = "250, 204, 21"; // 暖黄

function gridColor(intensity: number, alpha = 1): string {
  const t = Math.max(0, Math.min(1, intensity));
  const r = Math.round(160 + (255 - 160) * (1 - t));
  const g = Math.round(120 + (255 - 120) * (1 - t));
  const b = Math.round(250 + (255 - 250) * (1 - t));
  return `rgba(${r},${g},${b},${alpha})`;
}

/** 光点：angle 位置角度，radiusRatio 距中心比例（0~1） */
interface Blip {
  angle: number;
  radiusRatio: number;
  color: string;
}
const blips: Blip[] = [
  { angle: 0.9, radiusRatio: 0.92, color: COLOR_BLIP_BLUE },
  { angle: 2.2, radiusRatio: 0.62, color: COLOR_BLIP_ORANGE },
  { angle: 3.6, radiusRatio: 0.78, color: COLOR_BLIP_CYAN },
  { angle: 4.4, radiusRatio: 0.45, color: COLOR_BLIP_PINK },
  { angle: 5.6, radiusRatio: 0.85, color: COLOR_BLIP_YELLOW },
  { angle: 1.4, radiusRatio: 0.35, color: COLOR_BLIP_PINK },
  { angle: 2.9, radiusRatio: 0.88, color: COLOR_BLIP_BLUE },
  { angle: 4.0, radiusRatio: 0.55, color: COLOR_BLIP_YELLOW },
  { angle: 5.1, radiusRatio: 0.68, color: COLOR_BLIP_CYAN },
  { angle: 0.3, radiusRatio: 0.5, color: COLOR_BLIP_ORANGE },
];

/** 适配容器尺寸 + 高清屏（devicePixelRatio），否则 Retina 屏会模糊 */
function resizeCanvas() {
  const canvas = canvasRef.value;
  if (!canvas || !canvas.parentElement) return;
  const { width, height } = canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  ctx = canvas.getContext("2d");
  ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function drawFrame(timestamp: number) {
  const canvas = canvasRef.value;
  if (!canvas || !ctx) return;
  const c = ctx; // 本地别名：解除 TS 对 ctx 可能为 null 的收窄失效告警

  // 帧间隔（秒），首帧兜底为 0
  const dt = lastFrameTime ? (timestamp - lastFrameTime) / 1000 : 0;
  lastFrameTime = timestamp;
  sweepAngle = (sweepAngle + SWEEP_SPEED * dt) % SWEEP_PERIOD;

  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  const cx = w / 2;
  const cy = h / 2;
  const radius = Math.min(w, h) / 2 - 4; // 留一圈边距
  // 容器尺寸为 0（HMR / 布局变动瞬间）时 radius<=0，arc 半径负值会抛错使整帧崩溃、
  // RAF 链中断导致 canvas 永久空白。此处跳过绘制但保留动画循环，待尺寸恢复后自动继续。
  if (radius <= 0) {
    rafId = requestAnimationFrame(drawFrame);
    return;
  }

  c.clearRect(0, 0, w, h);

  // ---- 1. 网格：逐段绘制，被扫到的段更亮 ----
  const GRID_SLICES = 96; // 整圈切成 96 小段，段越小越平滑
  const step = (Math.PI * 2) / GRID_SLICES;

  // 同心圆：逐段画，段两端独立算强度 + 线性渐变描边，消除段间色差断层
  for (let i = 1; i <= 5; i++) {
    const r = (radius * i) / 5;
    const radialFactor = 0.35 + 0.65 * (r / radius);
    const baseAlpha = 1 - 0.75 * (r / radius); // 圆心≈1（亮），圆边≈0.25（淡）
    for (let s = 0; s < GRID_SLICES; s++) {
      const a0 = s * step; // 段起点角度
      const a1 = (s + 1) * step; // 段终点角度
      // diff = 扫线头部已扫过该段的角度（0~2π），只在尾巴内（≤TAIL_LENGTH）亮
      const diff0 = (sweepAngle - a0 + Math.PI * 2) % (Math.PI * 2);
      const diff1 = (sweepAngle - a1 + Math.PI * 2) % (Math.PI * 2);
      const i0 =
        diff0 > TAIL_LENGTH ? 0 : (1 - diff0 / TAIL_LENGTH) * radialFactor;
      const i1 =
        diff1 > TAIL_LENGTH ? 0 : (1 - diff1 / TAIL_LENGTH) * radialFactor;

      const alpha0 = baseAlpha + (1 - baseAlpha) * i0;
      const alpha1 = baseAlpha + (1 - baseAlpha) * i1;
      const x0 = cx + r * Math.cos(a0);
      const y0 = cy + r * Math.sin(a0);
      const x1 = cx + r * Math.cos(a1);
      const y1 = cy + r * Math.sin(a1);

      // 扫线头部落在本段内部时，在头部位置把段切开：
      // 否则该段会呈现"半紫半白 + 按两端平均加粗"的异常态，
      // 在待扫区紧贴头部出现一小段又白又粗的网格，逐格跳动造成闪烁
      if (a0 < sweepAngle && sweepAngle < a1) {
        const xh = cx + r * Math.cos(sweepAngle);
        const yh = cy + r * Math.sin(sweepAngle);
        // 已扫过部分（段起点 → 头部）：渐变到头部最亮
        const gradA = c.createLinearGradient(x0, y0, xh, yh);
        gradA.addColorStop(0, gridColor(i0, alpha0));
        gradA.addColorStop(1, gridColor(radialFactor, 1));
        const midA = (i0 + 1) / 2;
        c.beginPath();
        c.arc(cx, cy, r, a0, sweepAngle);
        c.strokeStyle = gradA;
        c.lineWidth = 1 + 2.5 * midA;
        if (midA > 0.7) {
          c.shadowColor = `rgba(${COLOR_SWEEP},${midA})`;
          c.shadowBlur = 10 * midA;
        }
        c.stroke();
        c.shadowBlur = 0;
        // 待扫部分（头部 → 段终点）：纯白细线，与其他待扫段一致
        c.beginPath();
        c.arc(cx, cy, r, sweepAngle, a1);
        c.strokeStyle = gridColor(0, baseAlpha);
        c.lineWidth = 1;
        c.stroke();
        continue;
      }

      // 用段两端切线方向的线性渐变，让整段内紫→白连续过渡
      const grad = c.createLinearGradient(x0, y0, x1, y1);
      grad.addColorStop(0, gridColor(i0, alpha0));
      grad.addColorStop(1, gridColor(i1, alpha1));

      // 发光和加粗沿用段中点强度（两端平均）
      const midI = (i0 + i1) / 2;

      c.beginPath();
      c.arc(cx, cy, r, a0, a1);
      c.strokeStyle = grad;
      c.lineWidth = 1 + 2.5 * midI;
      if (midI > 0.7) {
        c.shadowColor = `rgba(${COLOR_SWEEP},${midI})`;
        c.shadowBlur = 10 * midI;
      } else {
        c.shadowBlur = 0;
      }
      c.stroke();
    }
  }
  c.shadowBlur = 0; // 复位，避免污染后续绘制

  // 十字线：径向线段，两端同角度，单一强度即可（无需渐变，但保持接口统一）
  function drawRadialSegment(
    x0: number,
    y0: number,
    x1: number,
    y1: number,
    angle: number,
  ) {
    // diff = 扫线头部已扫过该段的角度（0~2π），只在尾巴内（≤TAIL_LENGTH）亮
    const diff = (sweepAngle - angle + Math.PI * 2) % (Math.PI * 2);
    const intensity = diff > TAIL_LENGTH ? 0 : 1 - diff / TAIL_LENGTH;

    const grad = c.createLinearGradient(x0, y0, x1, y1);
    grad.addColorStop(0, gridColor(intensity, 1));                        // 圆心端：亮
    grad.addColorStop(1, gridColor(intensity, 0.25 + 0.75 * intensity));  // 圆边端：淡
    c.beginPath();
    c.moveTo(x0, y0);
    c.lineTo(x1, y1);
    c.strokeStyle = grad;
    c.lineWidth = 1 + 2.5 * intensity;
    if (intensity > 0.7) {
      c.shadowColor = `rgba(${COLOR_SWEEP},${intensity})`;
      c.shadowBlur = 10 * intensity;
    } else {
      c.shadowBlur = 0;
    }
    c.stroke();
  }
  // 横轴
  drawRadialSegment(cx, cy, cx + radius, cy, 0);
  drawRadialSegment(cx, cy, cx - radius, cy, Math.PI);
  // 竖轴
  drawRadialSegment(cx, cy, cx, cy + radius, Math.PI / 2);
  drawRadialSegment(cx, cy, cx, cy - radius, Math.PI * 1.5);
  c.shadowBlur = 0; // 十字线绘制完毕，复位 shadow

  // ---- 2. 扫掠扇形 ----
  // 坑3：不用 createConicGradient（Safari 16.2+ 才支持），
  // 改用「沿尾巴切 N 个透明度递减的小扇形叠加」，效果相同且零兼容问题
  const SLICES = 48;
  for (let i = 0; i < SLICES; i++) {
    const ratio = 1 - i / SLICES; // 1 → 0，越往尾巴越透明
    const a1 = sweepAngle - (TAIL_LENGTH * i) / SLICES;
    const a0 = sweepAngle - (TAIL_LENGTH * (i + 1)) / SLICES;
    c.beginPath();
    c.moveTo(cx, cy);
    c.arc(cx, cy, radius, a0, a1);
    c.closePath();
    c.fillStyle = `rgba(${COLOR_SWEEP}, ${0.28 * ratio})`;
    c.fill();
  }
  // 扫掠前沿亮线
  c.beginPath();
  c.moveTo(cx, cy);
  c.lineTo(
    cx + radius * Math.cos(sweepAngle),
    cy + radius * Math.sin(sweepAngle),
  );
  const edgeX = cx + radius * Math.cos(sweepAngle);
  const edgeY = cy + radius * Math.sin(sweepAngle);
  const lineGrad = c.createLinearGradient(cx, cy, edgeX, edgeY);
  lineGrad.addColorStop(0, `rgba(${COLOR_SWEEP}, 0)`);
  lineGrad.addColorStop(1, `rgba(${COLOR_SWEEP}, 1)`);
  c.strokeStyle = lineGrad;
  c.lineWidth = 2;
  c.stroke();

  // ---- 3. 光点：仅被扫到才显示，带辉光，随角度差渐隐 ----
  for (const blip of blips) {
    // 光点位置固定，需把 sweepAngle 取模回单圈 [0,2π) 再算相对差，保证每圈都能重新扫到
    const rel = sweepAngle % (Math.PI * 2);
    const diff = (rel - blip.angle + Math.PI * 2) % (Math.PI * 2);
    const boost = Math.max(0, 1 - diff / BLIP_FADE); // 0~1，被扫到时为 1
    if (boost <= 0.02) continue; // 没被扫到就不显示

    const x = cx + radius * blip.radiusRatio * Math.cos(blip.angle);
    const y = cy + radius * blip.radiusRatio * Math.sin(blip.angle);

    // 单色光点：固定半径，半径不随 boost 变化（扫到出现、扫过淡出，不缩放）
    const r0 = Math.max(2.5, radius * 0.03); // 光点基础半径，随画布放大（保持原尺寸）
    const glowR = r0 * 2; // 光晕总半径，固定

    // 加法混合让光点在深色背景上变亮；只用 0→1 两 stop 的线性渐变，
    c.globalCompositeOperation = 'lighter';

    const g = c.createRadialGradient(x, y, 0, x, y, glowR);
    g.addColorStop(0,    `rgba(${blip.color},${boost})`);

    g.addColorStop(0.25, `rgba(${blip.color},${boost})`); // 核边开始快速淡
    g.addColorStop(1,    `rgba(${blip.color},0)`);          // 边缘透明
    c.beginPath();
    c.arc(x, y, glowR, 0, Math.PI * 2);
    c.fillStyle = g;
    c.fill();



    c.globalCompositeOperation = 'source-over'; // 复位混合模式，避免污染后续绘制
  }

  rafId = requestAnimationFrame(drawFrame);
}

onMounted(() => {
  resizeCanvas();
  // Canvas 不会自动跟随容器尺寸，用 ResizeObserver 监听
  resizeObserver = new ResizeObserver(resizeCanvas);
  resizeObserver.observe(canvasRef.value!.parentElement!);
  rafId = requestAnimationFrame(drawFrame);
});

onUnmounted(() => {
  // 坑2：必须取消动画帧，否则离开登录页后仍在空转（内存泄漏）
  cancelAnimationFrame(rafId);
  resizeObserver?.disconnect();
});
</script>

<template>
  <canvas ref="canvasRef" class="radar-canvas"></canvas>
</template>

<style scoped>
.radar-canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
