/** Framework-neutral DOM controls. Business state, auth, native actions and geometry remain host-owned. */
import {InvalidType, UnsupportedCapability, ValidationFailure, safeErrorReport} from './errors.js';
import type {ErrorReport} from './errors.js';
import type {BridgeSnapshot, Insets, TelegramBridge} from './bridge.js';
import {createTextField} from './shell.js';
import type {AppShell, TextFieldControl} from './shell.js';

export interface UiControl<E extends HTMLElement = HTMLElement> { readonly element: E; dispose(): void }
export type UiTone = 'neutral' | 'success' | 'warning' | 'danger';
export interface UiButtonOptions {
  label: string; variant?: 'primary' | 'secondary' | 'danger'; type?: 'button' | 'submit';
  onPress?: () => void | Promise<void>; onError?: (report: ErrorReport) => void;
}
export interface UiButton extends UiControl<HTMLButtonElement> {
  readonly pending: boolean;
  setPending(value: boolean): void;
  setDisabled(value: boolean): void;
}
function text(document: Document, tag: string, value: string, className = ''): HTMLElement {
  const element = document.createElement(tag); element.textContent = value; element.className = className; return element;
}
function requireText(value: string): void {
  if (typeof value !== 'string' || !value.trim() || value.length > 10000) throw new ValidationFailure('Use bounded UI text');
}
let sequence = 0;
function id(document: Document): string {
  let value: string;
  do {value = `tp-ui-${++sequence}`;} while (document.getElementById(value));
  return value;
}

/** Pending blocks activation without disabling the focused button or replacing its accessible label. */
export function createUiButton(document: Document, options: UiButtonOptions): UiButton {
  requireText(options.label);
  if (options.variant !== undefined && !['primary', 'secondary', 'danger'].includes(options.variant)) throw new ValidationFailure('Invalid button variant');
  if (options.type !== undefined && !['button', 'submit'].includes(options.type)) throw new ValidationFailure('Invalid button type');
  const element = document.createElement('button'); element.type = options.type ?? 'button';
  element.className = `tp-ui-button tp-ui-button--${options.variant ?? 'primary'}`; element.textContent = options.label;
  let busy = false, manual = false, disabled = false, disposed = false;
  const sync = () => {
    if (disposed) return;
    element.disabled = disabled; element.setAttribute('aria-busy', String(busy || manual));
    element.setAttribute('aria-disabled', String(disabled || busy || manual));
  };
  const press = (event: MouseEvent) => {
    if (disposed || disabled || busy || manual) {event.preventDefault(); return;}
    if (!options.onPress) return;
    // A managed submit action owns its submit; do not also dispatch the browser form request.
    if (element.type === 'submit') event.preventDefault();
    busy = true; sync();
    void Promise.resolve().then(() => disposed ? undefined : options.onPress?.()).catch((error: unknown) => {
      if (!disposed && options.onError) {try {options.onError(safeErrorReport(error, 'write'));} catch {/* best-effort UI reporter */}}
    }).finally(() => {busy = false; sync();});
  };
  element.addEventListener('click', press); sync();
  return {element, get pending() {return busy || manual;},
    setPending(value) {if (typeof value !== 'boolean') throw new InvalidType('Use boolean pending'); manual = value; sync();},
    setDisabled(value) {if (typeof value !== 'boolean') throw new InvalidType('Use boolean disabled'); disabled = value; sync();},
    dispose() {if (disposed) return; disposed = true; element.removeEventListener('click', press); element.remove();},
  };
}

export interface UiFieldOptions {
  label: string; hint?: string; value?: string; type?: 'text' | 'email' | 'tel' | 'number' | 'password' | 'date';
  inputMode?: 'none' | 'text' | 'decimal' | 'numeric' | 'tel' | 'search' | 'email' | 'url';
  autocomplete?: string; required?: boolean; validate?: (value: string) => string | null;
}
export interface UiField extends TextFieldControl {validate(): boolean; focus(): void; dispose(): void}
/** Reuses the existing field; errors never replace the input or clear its value/selection. */
export function createUiField(document: Document, options: UiFieldOptions): UiField {
  requireText(options.label);
  if (options.type !== undefined && !['text', 'email', 'tel', 'number', 'password', 'date'].includes(options.type)) throw new ValidationFailure('Invalid input type');
  if (options.inputMode !== undefined && !['none', 'text', 'decimal', 'numeric', 'tel', 'search', 'email', 'url'].includes(options.inputMode)) throw new ValidationFailure('Invalid input mode');
  const field = createTextField(document, options.required ? `${options.label} (обязательно)` : options.label, options.hint ?? ''); field.root.classList.add('tp-ui-field');
  field.input.type = options.type ?? 'text'; field.input.inputMode = options.inputMode ?? 'text';
  field.input.value = options.value ?? ''; field.input.required = options.required ?? false;
  if (options.autocomplete !== undefined) field.input.setAttribute('autocomplete', options.autocomplete);
  const validate = () => {
    const error = options.required && !field.input.value.trim() ? 'Заполните это поле.' : options.validate?.(field.input.value) ?? null;
    if (error !== null && typeof error !== 'string') throw new InvalidType('Validator must return string or null');
    field.setError(error); return !error;
  };
  const blur = () => {validate();}; field.input.addEventListener('blur', blur);
  return {...field, validate, focus() {field.input.focus();}, dispose() {field.input.removeEventListener('blur', blur); field.root.remove();}};
}
export function validateUiFields(fields: readonly UiField[]): boolean {
  let first: UiField | undefined;
  for (const field of fields) if (!field.validate()) first ??= field;
  first?.focus(); return first === undefined;
}

/** Same-origin navigation or public HTTPS only; no credentials, script/data URLs or control characters. */
export function uiUrl(value: string, base: string): string {
  if (typeof value !== 'string' || !value || value.length > 2048 || /[\u0000-\u0020\u007f]/.test(value)) throw new ValidationFailure('Invalid UI URL');
  let url: URL, origin: URL;
  try {origin = new URL(base); url = new URL(value, origin);} catch {throw new ValidationFailure('Invalid UI URL');}
  if (url.username || url.password || !['http:', 'https:'].includes(url.protocol) || (url.protocol !== 'https:' && url.origin !== origin.origin)) throw new ValidationFailure('Use same-origin or HTTPS UI navigation');
  return url.href;
}
export function createUiLink(document: Document, label: string, href: string): HTMLAnchorElement {
  requireText(label); const element = document.createElement('a'); element.textContent = label;
  element.href = uiUrl(href, document.baseURI); element.className = 'tp-ui-link';
  if (new URL(element.href).origin !== new URL(document.baseURI).origin) {element.target = '_blank'; element.rel = 'noopener noreferrer';}
  return element;
}
export function createUiBadge(document: Document, label: string, tone: UiTone = 'neutral'): HTMLElement {
  requireText(label); if (!['neutral', 'success', 'warning', 'danger'].includes(tone)) throw new ValidationFailure('Invalid badge tone');
  return text(document, 'span', label, `tp-ui-badge tp-ui-badge--${tone}`);
}
export function createUiCard(document: Document, title: string, description = ''): HTMLElement {
  requireText(title); const root = document.createElement('article'); root.className = 'tp-ui-card';
  root.append(text(document, 'h2', title)); if (description) root.append(text(document, 'p', description)); return root;
}
export interface UiListItem {title: string; detail?: string; badge?: string}
export function createUiList(document: Document, items: readonly UiListItem[], label: string): HTMLUListElement {
  requireText(label); const root = document.createElement('ul'); root.className = 'tp-ui-list'; root.setAttribute('aria-label', label);
  for (const item of items) {
    requireText(item.title); const row = document.createElement('li'); row.append(text(document, 'strong', item.title));
    if (item.detail) row.append(text(document, 'p', item.detail));
    if (item.badge) row.append(createUiBadge(document, item.badge)); root.append(row);
  } return root;
}
export function createUiSkeleton(document: Document, lines = 3): HTMLElement {
  if (!Number.isInteger(lines) || lines < 1 || lines > 12) throw new ValidationFailure('Use 1 to 12 skeleton lines');
  const root = document.createElement('div'); root.className = 'tp-ui-skeleton'; root.setAttribute('role', 'status');
  root.append(text(document, 'span', 'Загрузка…', 'tp-ui-sr-only'));
  for (let index = 0; index < lines; index++) {const line = document.createElement('span'); line.setAttribute('aria-hidden', 'true'); root.append(line);}
  return root;
}
export interface UiFeedbackOptions {kind: 'empty' | 'error' | 'success'; title: string; message: string; action?: UiButtonOptions}
export function createUiFeedback(document: Document, options: UiFeedbackOptions): UiControl {
  if (!['empty', 'error', 'success'].includes(options.kind)) throw new ValidationFailure('Invalid feedback state');
  const element = createUiCard(document, options.title, options.message); element.classList.add('tp-ui-feedback');
  element.dataset.state = options.kind; element.setAttribute('role', options.kind === 'error' ? 'alert' : 'status');
  const action = options.action ? createUiButton(document, options.action) : undefined;
  if (action) element.append(action.element);
  return {element, dispose() {action?.dispose(); element.remove();}};
}

export interface UiTab {id: string; label: string; content: HTMLElement}
export interface UiTabs extends UiControl {select(id: string): void; readonly selected: string}
export function createUiTabs(document: Document, label: string, tabs: readonly UiTab[]): UiTabs {
  requireText(label);
  if (!tabs.length || tabs.length > 20 || new Set(tabs.map(tab => tab.id)).size !== tabs.length || new Set(tabs.map(tab => tab.content)).size !== tabs.length) throw new ValidationFailure('Use distinct nonempty tabs and panels');
  tabs.forEach(tab => {requireText(tab.id); requireText(tab.label); if (tab.content.ownerDocument !== document) throw new ValidationFailure('Use same-document panels');});
  const element = document.createElement('div'); element.className = 'tp-ui-tabs';
  const list = document.createElement('div'); list.setAttribute('role', 'tablist'); list.setAttribute('aria-label', label); element.append(list);
  let selected = tabs[0]!.id, disposed = false;
  const buttons = tabs.map(tab => {
    const button = document.createElement('button'); button.type = 'button'; button.textContent = tab.label;
    button.id = id(document); button.setAttribute('role', 'tab'); tab.content.id ||= id(document);
    button.setAttribute('aria-controls', tab.content.id); tab.content.setAttribute('role', 'tabpanel');
    tab.content.setAttribute('aria-labelledby', button.id); tab.content.tabIndex = 0;
    list.append(button); element.append(tab.content); return button;
  });
  const select = (value: string) => {
    if (disposed) throw new ValidationFailure('Tabs already disposed');
    if (!tabs.some(tab => tab.id === value)) throw new ValidationFailure('Unknown tab'); selected = value;
    tabs.forEach((tab, index) => {buttons[index]!.tabIndex = tab.id === value ? 0 : -1; buttons[index]!.setAttribute('aria-selected', String(tab.id === value)); tab.content.hidden = tab.id !== value;});
  };
  const click = (event: Event) => {const index = buttons.indexOf(event.currentTarget as HTMLButtonElement); select(tabs[index]!.id);};
  const key = (event: KeyboardEvent) => {
    const current = buttons.indexOf(event.currentTarget as HTMLButtonElement);
    const index = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : event.key === 'ArrowRight' ? (current + 1) % tabs.length : event.key === 'ArrowLeft' ? (current + tabs.length - 1) % tabs.length : undefined;
    if (index !== undefined) {event.preventDefault(); select(tabs[index]!.id); buttons[index]!.focus();}
  };
  buttons.forEach(button => {button.addEventListener('click', click); button.addEventListener('keydown', key);}); select(selected);
  return {element, select, get selected() {return selected;}, dispose() {if (disposed) return; disposed = true; buttons.forEach(button => {button.removeEventListener('click', click); button.removeEventListener('keydown', key);}); element.remove();}};
}

export interface UiDialog extends UiControl<HTMLDialogElement> {readonly content: HTMLElement; open(opener?: HTMLElement): void; close(): void}
/** Native modality owns focus trapping/inert. Unsupported engines get an explicit capability error. */
export function createUiDialog(document: Document, title: string, variant: 'dialog' | 'sheet' = 'dialog'): UiDialog {
  requireText(title); if (!['dialog', 'sheet'].includes(variant)) throw new ValidationFailure('Invalid modal variant');
  const element = document.createElement('dialog'); element.className = `tp-ui-dialog tp-ui-dialog--${variant}`;
  const heading = text(document, 'h2', title); heading.id = id(document); heading.tabIndex = -1;
  element.setAttribute('aria-labelledby', heading.id); const content = document.createElement('div'); content.className = 'tp-ui-dialog-content';
  const closeButton = createUiButton(document, {label: 'Закрыть', variant: 'secondary', onPress: () => close()});
  element.append(heading, content, closeButton.element);
  let opener: HTMLElement | undefined, disposed = false;
  const restore = () => {if (element.open) return; const target = opener; opener = undefined; if (target?.isConnected) target.focus();};
  const close = () => {if (element.open) element.close(); restore();};
  const cancel = (event: Event) => {event.preventDefault(); close();};
  const key = (event: KeyboardEvent) => {
    if (event.key !== 'Tab' || !element.open) return;
    const controls = Array.from(element.querySelectorAll<HTMLElement>('button,a[href],input,select,textarea,[tabindex]'))
      .filter(control => control.tabIndex >= 0 && !control.hasAttribute('disabled') && control.getClientRects().length > 0);
    const current = controls.indexOf(document.activeElement as HTMLElement);
    if (controls.length && (event.shiftKey ? current <= 0 : current < 0 || current === controls.length - 1)) {
      event.preventDefault(); controls[event.shiftKey ? controls.length - 1 : 0]!.focus();
    }
  };
  const backdrop = (event: MouseEvent) => {
    if (event.target !== element) return; const rect = element.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) close();
  };
  element.addEventListener('cancel', cancel); element.addEventListener('close', restore); element.addEventListener('click', backdrop); element.addEventListener('keydown', key);
  return {element, content,
    open(trigger) {
      if (disposed) throw new ValidationFailure('Dialog already disposed'); if (element.open) return;
      if (typeof element.showModal !== 'function') throw new UnsupportedCapability('Native modal dialogs are unavailable');
      opener = trigger ?? document.activeElement as HTMLElement | undefined;
      element.showModal(); heading.focus();
    }, close,
    dispose() {if (disposed) return; close(); disposed = true; closeButton.dispose(); element.removeEventListener('cancel', cancel); element.removeEventListener('close', restore); element.removeEventListener('click', backdrop); element.removeEventListener('keydown', key); element.remove();},
  };
}

export interface UiShellOptions {resolveInsets?: (snapshot: BridgeSnapshot) => Insets | undefined}
/** Borrow the existing bridge/shell; native theme wins. Insets are resolved once by host, never summed here. */
export function connectUiShell(shell: AppShell, bridge: Pick<TelegramBridge, 'subscribe'>, options: UiShellOptions = {}): () => void {
  const window = shell.element.ownerDocument.defaultView;
  const media = window?.matchMedia?.('(prefers-color-scheme: dark)'); let latest: BridgeSnapshot | undefined;
  const apply = () => {
    if (!latest) return;
    shell.applyTheme(latest.insideTelegram ? latest : {...latest, colorScheme: media?.matches ? 'dark' : 'light', theme: {}});
    if (options.resolveInsets) {
      const resolved = options.resolveInsets(latest);
      if (resolved) shell.setInsets(resolved);
      else for (const side of ['top', 'right', 'bottom', 'left']) shell.element.style.removeProperty(`--tp-inset-${side}`);
    }
  };
  const unsubscribe = bridge.subscribe(snapshot => {latest = snapshot; apply();}); media?.addEventListener('change', apply);
  let disposed = false;
  return () => {if (disposed) return; disposed = true; unsubscribe(); media?.removeEventListener('change', apply);};
}
/** Visibility repair, not a keyboard detector; no fixed CTA or dynamic viewport-height writes. */
export function bindUiFocusVisibility(root: HTMLElement): () => void {
  const window = root.ownerDocument.defaultView; if (!window) return () => {};
  let frame: number | undefined;
  const check = () => {
    frame = undefined; const active = root.ownerDocument.activeElement;
    if (!(active instanceof window.HTMLElement) || !root.contains(active) || !active.matches('input,textarea,select,[contenteditable=true]')) return;
    const viewport = window.visualViewport; const top = viewport?.offsetTop ?? 0, bottom = top + (viewport?.height ?? window.innerHeight);
    const rect = active.getBoundingClientRect(); if (rect.top < top || rect.bottom > bottom) active.scrollIntoView({block: 'nearest', behavior: 'instant'});
  };
  const schedule = () => {if (frame === undefined) frame = window.requestAnimationFrame(check);};
  root.addEventListener('focusin', schedule); window.visualViewport?.addEventListener('resize', schedule); window.addEventListener('pageshow', schedule);
  return () => {root.removeEventListener('focusin', schedule); window.visualViewport?.removeEventListener('resize', schedule); window.removeEventListener('pageshow', schedule); if (frame !== undefined) window.cancelAnimationFrame(frame); frame = undefined;};
}
