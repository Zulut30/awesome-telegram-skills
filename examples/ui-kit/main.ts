/** Explicit local read fixture: no Telegram identity, backend, payment or delivery is simulated as production. */
import {createAppShell} from '@awesome-telegram/patterns';
import {bindUiFocusVisibility, connectUiShell, createUiBadge, createUiButton, createUiDialog, createUiFeedback,
  createUiCard, createUiTabs} from '@awesome-telegram/patterns';
import type {BridgeSnapshot} from '@awesome-telegram/patterns';
import {createBookingScreen, createCartScreen, createCatalogScreen, createProductScreen,
  createProfileScreen, createSettingsScreen} from './screens.js';

const shell = createAppShell(document.querySelector<HTMLElement>('#app')!, 'Ваш следующий шаг');
const lead = document.createElement('p'); lead.textContent = 'Локальное превью компонентов. Данные учебные; подключения к Telegram, платежей и подтверждения записи нет.'; shell.content.append(lead);
let snapshot: BridgeSnapshot = {insideTelegram: false, colorScheme: 'light', theme: {}, stableHeight: undefined, systemInsets: undefined, contentInsets: undefined};
const subscribers = new Set<(value: BridgeSnapshot) => void>();
const disconnect = connectUiShell(shell, {subscribe(listener) {subscribers.add(listener); listener(snapshot); return () => {subscribers.delete(listener);};}});
const focusCleanup = bindUiFocusVisibility(shell.element);
const panels = ['Каталог', 'Товар', 'Корзина', 'Профиль', 'Настройки', 'Запись'].map(label => ({id: label, label, content: document.createElement('section')}));
const tabs = createUiTabs(document, 'Разделы примера', panels); shell.content.append(tabs.element);
const modal = createUiDialog(document, 'Обзор выбранного действия', 'sheet'); shell.element.append(modal.element);
const show = (message: string) => {modal.content.replaceChildren(document.createTextNode(message)); modal.open();};
type Mode = 'ready' | 'loading' | 'empty' | 'error';
let mode: Mode = 'ready';
const service = <T>(value: T) => ({scope: 'explicit-local-preview', async load({signal}: {signal: AbortSignal}) {
  if (mode === 'loading') return await new Promise<T | null>((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Stopped', 'AbortError')), {once: true}));
  await new Promise(resolve => setTimeout(resolve, 20)); if (mode === 'error') throw Error('PRIVATE_SERVER_CANARY');
  return mode === 'empty' ? null : value;
}});
const product = {id: 'consultation', title: 'Разбор проекта Telegram Mini App и плана развития',
  description: 'Обсудим структуру, ограничения клиента и ближайшую полезную задачу. Длинное название и текст помогают проверить переносы.', priceLabel: 'Стоимость приходит с сервера'};
const views = [
  createCatalogScreen(panels[0]!.content, service({items: [product, {...product, id: 'review', title: 'Проверка интерфейса и сценария исправления ошибок'}]}), () => tabs.select('Товар')),
  createProductScreen(panels[1]!.content, service(product), async () => {show('В этом локальном превью действие передаётся владельцу корзины. Заказ и оплата не создаются.');}),
  createCartScreen(panels[2]!.content, service({items: [{title: product.title, quantityLabel: '1 услуга'}], totalLabel: 'Итог проверяет backend', terms: 'До подтверждения покажите фактическую цену, валюту, срок и условия.'}), () => show('Здесь проект подключает проверку заказа на сервере.')),
  createProfileScreen(panels[3]!.content, service({displayName: 'Учебный профиль', details: [{title: 'Данные', detail: 'Сервис получает их из подтверждённой сессии.'}]})),
  createSettingsScreen(panels[4]!.content, {...service({name: 'Александра', email: 'preview@example.org'}), async save() {throw Error('PRIVATE_SAVE_CANARY');}}),
  createBookingScreen(panels[5]!.content, service({serviceTitle: 'Выберите удобное время', slots: [{id: 'a', label: 'Понедельник — с 10:30 до 11:15 по вашему часовому поясу'}, {id: 'b', label: 'Вторник — с 15:00 до 15:45'}], explanation: 'Слот проверяется сервером ещё раз перед записью.'}), () => show('Слот выбран для обзора. Запись в этом превью не подтверждается.')),
];
const controls = document.querySelector<HTMLElement>('#preview-controls')!;
const controlCleanup: Array<() => void> = [];
for (const value of ['ready', 'loading', 'empty', 'error'] as const) {
  const button = createUiButton(document, {label: `Состояние: ${value}`, variant: 'secondary', onPress: async () => {mode = value; await Promise.all(views.map(view => view.reload()));}});
  controls.append(button.element);
  controlCleanup.push(() => button.dispose());
}
const theme = createUiButton(document, {label: 'Переключить тему превью', onPress: () => {
  snapshot = {...snapshot, insideTelegram: true, colorScheme: snapshot.colorScheme === 'light' ? 'dark' : 'light'};
  for (const listener of subscribers) listener(snapshot);
}}); controls.append(theme.element);
shell.summary.append(createUiBadge(document, 'Общая система', 'success'), createUiBadge(document, 'Нужна проверка клиента', 'warning'));
shell.summary.append(createUiBadge(document, 'Ошибка требует исправления', 'danger'));
const variants = createUiCard(document, 'Состояния компонентов', 'Образцы действий: ожидание связано с локальным Promise; бизнес-запрос не выполняется.');
const variantActions = document.createElement('div'); variantActions.className = 'tp-ui-actions'; variants.append(variantActions);
for (const variant of ['primary', 'secondary', 'danger'] as const) {
  const button = createUiButton(document, {label: variant === 'danger' ? 'Опасное действие (образец)' : variant === 'secondary' ? 'Дополнительное действие' : 'Проверить ожидание', variant,
    onPress: async () => {await new Promise(resolve => setTimeout(resolve, 300));}});
  variantActions.append(button.element); controlCleanup.push(() => button.dispose());
}
const disabled = createUiButton(document, {label: 'Недоступно: нет выбранного элемента'}); disabled.setDisabled(true); variantActions.append(disabled.element);
controlCleanup.push(() => disabled.dispose()); shell.summary.append(variants);
const feedback = createUiFeedback(document, {kind: 'success', title: 'Компоненты готовы к композиции', message: 'Это статус интерфейса, а не подтверждение оплаты или доставки.'}); shell.summary.append(feedback.element);
window.addEventListener('pagehide', event => {if (event.persisted) return; controlCleanup.forEach(dispose => dispose()); theme.dispose(); views.forEach(view => view.dispose()); tabs.dispose(); modal.dispose(); feedback.dispose(); disconnect(); focusCleanup(); shell.dispose();});
// Browser tests drive actual controls and inspect this explicit fixture, never a production global.
Object.assign(window, {uiPreview: {shell, tabs, modal, views, setMode(value: Mode) {mode = value; return Promise.all(views.map(view => view.reload()));}}});
