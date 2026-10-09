import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => cleanup());

// jsdom does not implement these browser APIs
if (!window.matchMedia) {
  window.matchMedia = ((q: string) => ({ matches: false, media: q, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false })) as typeof window.matchMedia;
}
window.scrollTo = (() => {}) as typeof window.scrollTo;
Element.prototype.scrollTo = (() => {}) as typeof Element.prototype.scrollTo;
Element.prototype.scrollBy = (() => {}) as typeof Element.prototype.scrollBy;
