import type { BridgeSnapshot, Insets } from './bridge.js';

export interface TextFieldControl {
  root: HTMLDivElement;
  input: HTMLInputElement;
  setError(text: string | null): void;
}

export interface AppShell {
  readonly element: HTMLElement;
  readonly content: HTMLElement;
  readonly summary: HTMLElement;
  readonly actions: HTMLElement;
  applyTheme(snapshot: BridgeSnapshot): void;
  setInsets(resolved: Insets): void;
  dispose(): void;
}
/** Host owns safe-area resolution; never guess sum/max of different coordinates. */
export function createAppShell(host: HTMLElement, title: string): AppShell {
  const document = host.ownerDocument;
  const element = document.createElement('main'); element.className = 'tp-shell';
  const heading = document.createElement('h1'); heading.textContent = title;
  const columns = document.createElement('div'); columns.className = 'tp-columns';
  const content = document.createElement('section'); content.className = 'tp-panel';
  const summary = document.createElement('aside'); summary.className = 'tp-panel tp-summary';
  summary.setAttribute('aria-label', 'Обзор');
  const actions = document.createElement('div'); actions.className = 'tp-actions';
  columns.append(content, summary); element.append(heading, columns, actions); host.append(element);
  return {
    element, content, summary, actions,
    applyTheme(snapshot) {
      element.dataset.theme = snapshot.colorScheme;
      const colors: Record<string, readonly string[]> = {
        '--tp-bg': ['bg_color'], '--tp-text': ['text_color'],
        '--tp-action': ['button_color'], '--tp-action-text': ['button_text_color'],
        '--tp-surface': ['section_bg_color', 'secondary_bg_color'],
        '--tp-muted': ['hint_color'], '--tp-border': ['section_separator_color'],
        '--tp-error': ['destructive_text_color'],
      };
      for (const [css, keys] of Object.entries(colors)) {
        const value = keys.map(key => snapshot.theme[key]).find(color => color !== undefined && /^#[0-9a-f]{6}$/i.test(color));
        if (value) element.style.setProperty(css, value);
        else element.style.removeProperty(css);
      }
      if (snapshot.stableHeight !== undefined) element.style.setProperty('--tp-stable-height', `${snapshot.stableHeight}px`);
      else element.style.removeProperty('--tp-stable-height');
    },
    setInsets(resolved) {
      for (const key of ['top', 'right', 'bottom', 'left'] as const) {
        if (!Number.isFinite(resolved[key]) || resolved[key] < 0) throw new Error('Invalid resolved inset');
      }
      for (const key of ['top', 'right', 'bottom', 'left'] as const) element.style.setProperty(`--tp-inset-${key}`, `${resolved[key]}px`);
    },
    dispose() { element.remove(); },
  };
}

let sequence = 0;
export function createTextField(document: Document, label: string, hint = ''): TextFieldControl {
  const root = document.createElement('div'); root.className = 'tp-field';
  let id: string;
  do { id = `tp-field-${document.defaultView?.crypto?.randomUUID?.() ?? ++sequence}`; }
  while ([id, `${id}-hint`, `${id}-error`].some(candidate => document.getElementById(candidate)));
  const caption = document.createElement('label'); caption.htmlFor = id; caption.textContent = label;
  const input = document.createElement('input'); input.id = id;
  const help = document.createElement('p'); help.id = `${id}-hint`; help.className = 'tp-hint'; help.textContent = hint;
  const error = document.createElement('p'); error.id = `${id}-error`; error.className = 'tp-error'; error.setAttribute('role', 'alert'); error.hidden = true;
  input.setAttribute('aria-describedby', help.id);
  root.append(caption, input, help, error);
  return {root, input, setError(text: string | null) {
    error.textContent = text ?? ''; error.hidden = !text;
    input.setAttribute('aria-invalid', text ? 'true' : 'false');
    input.setAttribute('aria-describedby', text ? `${help.id} ${error.id}` : help.id);
  }};
}
