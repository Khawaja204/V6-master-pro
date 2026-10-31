// Order block rectangles (lightweight-charts primitive, apna implementation).
// Visual idea LuxAlgo "Smart Money Concepts" (c) LuxAlgo se hai, license CC BY-NC-SA 4.0.
// Sirf non-commercial istemal.

export interface ZoneRect {
  t1: number;
  t2: number;
  top: number;
  bottom: number;
  fill: string;
  border: string;
}

class ZoneRenderer {
  private rects: ZoneRect[];
  private ts: any;
  private series: any;

  constructor(rects: ZoneRect[], ts: any, series: any) {
    this.rects = rects;
    this.ts = ts;
    this.series = series;
  }

  draw(target: any) {
    target.useMediaCoordinateSpace(({ context: ctx }: any) => {
      for (const r of this.rects) {
        const x1 = this.ts.timeToCoordinate(r.t1);
        const x2 = this.ts.timeToCoordinate(r.t2);
        const y1 = this.series.priceToCoordinate(r.top);
        const y2 = this.series.priceToCoordinate(r.bottom);
        if (x1 === null || x2 === null || y1 === null || y2 === null) continue;
        const w = Math.max(x2 - x1, 2);
        const h = Math.max(y2 - y1, 1);
        ctx.fillStyle = r.fill;
        ctx.fillRect(x1, y1, w, h);
        ctx.strokeStyle = r.border;
        ctx.lineWidth = 1;
        ctx.strokeRect(x1, y1, w, h);
      }
    });
  }
}

class ZonePane {
  private r: ZoneRenderer;

  constructor(r: ZoneRenderer) {
    this.r = r;
  }

  zOrder() {
    return "bottom";
  }

  renderer() {
    return this.r;
  }

  update() {}
}

export class ZonePrimitive {
  private rects: ZoneRect[];
  private view: ZonePane | null = null;

  constructor(rects: ZoneRect[]) {
    this.rects = rects;
  }

  attached(param: any) {
    this.view = new ZonePane(new ZoneRenderer(this.rects, param.chart.timeScale(), param.series));
  }

  detached() {
    this.view = null;
  }

  paneViews() {
    return this.view ? [this.view] : [];
  }

  updateAllViews() {}
}
