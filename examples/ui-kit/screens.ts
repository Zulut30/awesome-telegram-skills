/** Reusable compositions: services own verified scope, DTO validation and all domain writes. */
import {ScopedAsyncState, ValidationFailure} from '@awesome-telegram/patterns';
import type {AsyncReadContext} from '@awesome-telegram/patterns';
import {createUiBadge, createUiButton, createUiCard, createUiFeedback, createUiField,
  createUiList, createUiSkeleton, validateUiFields} from '@awesome-telegram/patterns';
import type {UiControl} from '@awesome-telegram/patterns';

export interface ScreenService<T> {readonly scope: string; load(context: AsyncReadContext): Promise<T | null>}
export interface ScreenView extends UiControl {readonly state: 'loading' | 'empty' | 'error' | 'ready' | 'disposed'; reload(): Promise<void>}
type Render<T> = (value: T, root: HTMLElement, owned: Array<() => void>) => void;
function mount<T>(host: HTMLElement, title: string, service: ScreenService<T>, empty: (value: T) => boolean, render: Render<T>): ScreenView {
  const document = host.ownerDocument, element = document.createElement('section'); element.className = 'tp-ui-screen';
  if (!service || typeof service.scope !== 'string' || !service.scope || typeof service.load !== 'function') throw new ValidationFailure('Use an injected screen service with verified scope');
  element.setAttribute('aria-label', title);
  const state = new ScopedAsyncState<T | null>({maxEntries: 1}); state.setScope(service.scope);
  host.append(element);
  let phase: ScreenView['state'] = 'loading'; let owned: Array<() => void> = [];
  const clear = () => {for (const dispose of owned) dispose(); owned = []; element.replaceChildren();};
  const view: ScreenView = {element, get state() {return phase;}, async reload() {
    if (phase === 'disposed') return;
    clear(); phase = 'loading'; element.setAttribute('aria-busy', 'true'); element.append(createUiSkeleton(document));
    const result = await state.read('screen', context => service.load(context));
    if (result.status === 'stale' || view.state === 'disposed') return;
    clear(); element.setAttribute('aria-busy', 'false');
    if (result.status === 'failed') {
      phase = 'error'; const feedback = createUiFeedback(document, {kind: 'error', title: 'Не удалось загрузить',
        message: 'Попробуйте получить данные ещё раз. Ваши изменения сохранены на этом экране.',
        action: {label: 'Повторить загрузку', onPress: () => view.reload()}});
      owned.push(() => feedback.dispose()); element.append(feedback.element);
    } else if (result.value === null || empty(result.value)) {
      phase = 'empty'; const feedback = createUiFeedback(document, {kind: 'empty', title: 'Пока ничего нет', message: 'Данные появятся здесь, когда они будут доступны.'});
      owned.push(() => feedback.dispose()); element.append(feedback.element);
    } else {phase = 'ready'; render(result.value, element, owned);}
  }, dispose() {if (phase === 'disposed') return; phase = 'disposed'; state.dispose(); clear(); element.remove();}};
  void view.reload(); return view;
}
function action(root: HTMLElement, owned: Array<() => void>, label: string, call: () => void | Promise<void>): void {
  const document = root.ownerDocument;
  const button = createUiButton(document, {label, onPress: call, onError: report => {
    const feedback = createUiFeedback(document, {kind: 'error', title: 'Действие не подтверждено', message: report.message});
    owned.push(() => feedback.dispose()); root.append(feedback.element);
  }});
  owned.push(() => button.dispose()); root.append(button.element);
}

export interface Product {id: string; title: string; description: string; priceLabel: string}
export interface Catalog {items: readonly Product[]}
export function createCatalogScreen(host: HTMLElement, service: ScreenService<Catalog>, open: (id: string) => void): ScreenView {
  return mount(host, 'Каталог', service, model => model.items.length === 0, (model, root, owned) => {
    const grid = root.ownerDocument.createElement('div'); grid.className = 'tp-ui-grid'; root.append(grid);
    for (const product of model.items) {const card = createUiCard(root.ownerDocument, product.title, product.description);
      card.append(createUiBadge(root.ownerDocument, product.priceLabel)); action(card, owned, 'Подробнее', () => open(product.id)); grid.append(card);}
  });
}
export function createProductScreen(host: HTMLElement, service: ScreenService<Product>, add: (id: string) => Promise<void>): ScreenView {
  return mount(host, 'Товар', service, () => false, (product, root, owned) => {
    const card = createUiCard(root.ownerDocument, product.title, product.description); card.append(createUiBadge(root.ownerDocument, product.priceLabel));
    action(card, owned, 'Добавить в корзину', () => add(product.id)); root.append(card);
  });
}
export interface Cart {items: readonly {title: string; quantityLabel: string}[]; totalLabel: string; terms: string}
export function createCartScreen(host: HTMLElement, service: ScreenService<Cart>, review: () => void): ScreenView {
  return mount(host, 'Корзина', service, model => model.items.length === 0, (model, root, owned) => {
    root.append(createUiList(root.ownerDocument, model.items.map(item => ({title: item.title, detail: item.quantityLabel})), 'Товары в корзине'),
      createUiCard(root.ownerDocument, model.totalLabel, model.terms));
    action(root, owned, 'Проверить заказ', review); // navigation only: no payment success invented here
  });
}
export interface Profile {displayName: string; details: readonly {title: string; detail: string}[]}
export function createProfileScreen(host: HTMLElement, service: ScreenService<Profile>): ScreenView {
  return mount(host, 'Профиль', service, () => false, (model, root) => {
    root.append(createUiCard(root.ownerDocument, model.displayName), createUiList(root.ownerDocument, model.details, 'Данные профиля'));
  });
}
export interface Settings {name: string; email: string}
export interface SettingsService extends ScreenService<Settings> {save(value: Settings): Promise<void>}
export function createSettingsScreen(host: HTMLElement, service: SettingsService): ScreenView {
  let draft: Settings | undefined;
  return mount(host, 'Настройки', service, () => false, (model, root, owned) => {
    draft ??= {...model}; const document = root.ownerDocument;
    const name = createUiField(document, {label: 'Как к вам обращаться', required: true, value: draft.name, autocomplete: 'name'});
    const email = createUiField(document, {label: 'Электронная почта', type: 'email', inputMode: 'email', autocomplete: 'email', value: draft.email,
      validate: value => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) ? null : 'Укажите адрес в формате name@example.org.'});
    const remember = () => {draft = {name: name.input.value, email: email.input.value};};
    for (const field of [name, email]) {field.input.addEventListener('input', remember); owned.push(() => {remember(); field.input.removeEventListener('input', remember); field.dispose();}); root.append(field.root);}
    const status = document.createElement('p'); status.setAttribute('role', 'status'); root.append(status);
    action(root, owned, 'Сохранить настройки', async () => {
      if (!validateUiFields([name, email])) return;
      remember(); const submitted = {...draft!}; await service.save(submitted);
      status.textContent = name.input.value === submitted.name && email.input.value === submitted.email
        ? 'Настройки сохранены.' : 'Предыдущие значения сохранены. Текущие изменения ещё не отправлены.';
    });
  });
}
export interface Booking {serviceTitle: string; slots: readonly {id: string; label: string}[]; explanation: string}
export function createBookingScreen(host: HTMLElement, service: ScreenService<Booking>, select: (slot: string) => void): ScreenView {
  return mount(host, 'Запись', service, model => model.slots.length === 0, (model, root, owned) => {
    root.append(createUiCard(root.ownerDocument, model.serviceTitle, model.explanation));
    for (const slot of model.slots) action(root, owned, slot.label, () => select(slot.id));
  });
}
