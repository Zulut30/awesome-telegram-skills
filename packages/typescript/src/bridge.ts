export interface Insets { readonly top: number; readonly right: number; readonly bottom: number; readonly left: number }
export interface TelegramWebApp {
  readonly platform?: string;
  readonly colorScheme?: string;
  readonly themeParams?: Readonly<Record<string, string | undefined>>;
  readonly viewportStableHeight?: number;
  readonly safeAreaInset?: Insets;
  readonly contentSafeAreaInset?: Insets;
  ready(): void;
  onEvent(event: string, listener: () => void): void;
  offEvent(event: string, listener: () => void): void;
}
export interface BridgeSnapshot {
  readonly insideTelegram: boolean;
  readonly colorScheme: 'light' | 'dark';
  readonly theme: Readonly<Record<string, string>>;
  readonly stableHeight: number | undefined;
  readonly systemInsets: Insets | undefined;
  readonly contentInsets: Insets | undefined;
}
const EVENTS = ['themeChanged', 'viewportChanged', 'safeAreaChanged', 'contentSafeAreaChanged'] as const;
function insets(value: Insets | undefined): Insets | undefined {
  if (!value) return undefined;
  const entries = [value.top, value.right, value.bottom, value.left];
  if (entries.some(n => !Number.isFinite(n) || n < 0)) return undefined;
  return Object.freeze({ top: value.top, right: value.right, bottom: value.bottom, left: value.left });
}

/** Owns subscriptions only; this snapshot never establishes server identity. */
export class TelegramBridge {
  private started = false;
  private attached = false;
  private disposed = false;
  private readySent = false;
  private readonly listeners = new Set<(snapshot: BridgeSnapshot) => void>();
  private readonly changed = () => this.emit();
  private readonly hide = () => this.detach();
  private readonly show = () => { if (this.started && !this.disposed) { this.attach(); this.emit(); } };
  constructor(private readonly app: TelegramWebApp | undefined,
              private readonly lifecycle: EventTarget | undefined = typeof window === 'undefined' ? undefined : window) {}

  snapshot(): BridgeSnapshot {
    const theme: Record<string, string> = {};
    for (const [name, value] of Object.entries(this.app?.themeParams ?? {})) {
      if (value && /^#[0-9a-f]{6}$/i.test(value)) theme[name] = value;
    }
    const height = this.app?.viewportStableHeight;
    return Object.freeze({
      insideTelegram: this.app !== undefined && this.app.platform !== 'unknown',
      colorScheme: this.app?.colorScheme === 'dark' ? 'dark' : 'light',
      theme: Object.freeze(theme),
      stableHeight: height !== undefined && Number.isFinite(height) && height > 0 ? height : undefined,
      systemInsets: insets(this.app?.safeAreaInset), contentInsets: insets(this.app?.contentSafeAreaInset),
    });
  }
  subscribe(listener: (snapshot: BridgeSnapshot) => void): () => void {
    if (this.disposed) throw new Error('Bridge already disposed');
    this.listeners.add(listener);
    try { listener(this.snapshot()); }
    catch (error) { this.listeners.delete(listener); throw error; }
    return () => { this.listeners.delete(listener); };
  }
  start(): void {
    if (this.disposed) throw new Error('Bridge already disposed');
    if (this.started) return;
    this.started = true;
    try {
      this.lifecycle?.addEventListener('pagehide', this.hide);
      this.lifecycle?.addEventListener('pageshow', this.show);
      this.attach();
      if (this.app && !this.readySent) { this.app.ready(); this.readySent = true; }
      this.emit();
    } catch (error) {
      this.started = false;
      this.detach();
      this.lifecycle?.removeEventListener('pagehide', this.hide);
      this.lifecycle?.removeEventListener('pageshow', this.show);
      throw error;
    }
  }
  dispose(): void {
    this.detach();
    this.lifecycle?.removeEventListener('pagehide', this.hide);
    this.lifecycle?.removeEventListener('pageshow', this.show);
    this.listeners.clear();
    this.started = false;
    this.disposed = true;
  }
  private attach(): void {
    if (this.attached || !this.app) return;
    this.attached = true;
    try { for (const event of EVENTS) this.app.onEvent(event, this.changed); }
    catch (error) { this.detach(); throw error; }
  }
  private detach(): void {
    if (!this.attached || !this.app) return;
    for (const event of EVENTS) this.app.offEvent(event, this.changed);
    this.attached = false;
  }
  private emit(): void {
    const value = this.snapshot();
    for (const listener of this.listeners) listener(value);
  }
}
